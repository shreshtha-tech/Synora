"""Select Pinecone's API by the configured index schema, never by SDK age."""
import asyncio
from functools import lru_cache
from itertools import islice
from types import SimpleNamespace

from pinecone import Pinecone
import google.generativeai as genai

from app.core.config import get_settings
from app.services.parallel import together, offload

settings = get_settings()
genai.configure(api_key=settings.GEMINI_API_KEY)
_embedding_slots = asyncio.Semaphore(settings.EMBEDDING_CONCURRENCY)


async def _write_documents(document_id, documents):
    response = await offload(lambda: _index().documents.upsert(namespace=document_id, documents=documents, timeout=120))
    if response.upserted_count != len(documents):
        raise ValueError('Pinecone did not acknowledge all document chunks')


@lru_cache()
def _client():
    return Pinecone(api_key=settings.PINECONE_API_KEY)


@lru_cache()
def _index():
    return _client().Index(settings.PINECONE_INDEX_NAME)


@lru_cache()
def _layout():
    description = _client().indexes.describe(settings.PINECONE_INDEX_NAME).to_dict()
    fields = (description.get('schema') or {}).get('fields', {})
    embedded = [name for name, field in fields.items() if field.get('embed')]
    dense = [name for name, field in fields.items() if field.get('type') == 'dense_vector']
    if embedded:
        if len(embedded) != 1 or dense:
            raise ValueError('Synora requires one integrated text embedding field and no required dense fields')
        return {'mode': 'integrated', 'text_field': embedded[0]}
    if fields:
        if len(dense) != 1:
            raise ValueError('Synora requires one dense vector or integrated text field')
        return {'mode': 'documents', 'vector_field': dense[0], 'dimension': fields[dense[0]]['dimension']}
    return {'mode': 'vectors', 'dimension': description['dimension']}


async def generate_embedding(text: str) -> list:
    layout = await offload(_layout)
    async with _embedding_slots:
        result = await genai.embed_content_async(
            model='models/gemini-embedding-001', content=text,
            task_type='retrieval_document', output_dimensionality=layout.get('dimension', 768),
            request_options={'timeout': 120},
        )
    return result['embedding']


async def _upsert_batch(document_id: str, batch: list):
    async with _embedding_slots:
        layout = await offload(_layout)
        if layout['mode'] == 'integrated':
            # The configured schema owns its embedding model/dimension. Sending
            # unrelated Gemini vectors here is invalid and wastes a provider call.
            documents = [
                {'_id': f'{document_id}_{i}', layout['text_field']: chunk,
                 'document_id': document_id, 'chunk_index': i}
                for i, chunk in batch
            ]
            await _write_documents(document_id, documents)
            return
        result = await genai.embed_content_async(
            model='models/gemini-embedding-001', content=[chunk for _, chunk in batch],
            task_type='retrieval_document', output_dimensionality=layout['dimension'],
            request_options={'timeout': 120},
        )
        embeddings = result['embedding']
        if len(embeddings) != len(batch):
            raise ValueError('Embedding provider returned an incomplete batch')
        if layout['mode'] == 'documents':
            documents = [
                {'_id': f'{document_id}_{i}', layout['vector_field']: embedding,
                 'document_id': document_id, 'text': chunk, 'chunk_index': i}
                for (i, chunk), embedding in zip(batch, embeddings)
            ]
            await _write_documents(document_id, documents)
        else:
            vectors = [
                {'id': f'{document_id}_{i}', 'values': embedding,
                 'metadata': {'document_id': document_id, 'text': chunk, 'chunk_index': i}}
                for (i, chunk), embedding in zip(batch, embeddings)
            ]
            await offload(lambda: _index().upsert(vectors=vectors))


async def upsert_vectors(document_id: str, chunks):
    indexed = enumerate(chunks)
    # Integrated embedding upserts support at most 96 records per request.
    layout = await offload(_layout)
    size = min(settings.EMBEDDING_BATCH_SIZE, 96 if layout['mode'] == 'integrated' else 100)
    while True:
        batches = []
        for _ in range(settings.EMBEDDING_CONCURRENCY):
            batch = list(islice(indexed, size))
            if not batch:
                break
            batches.append(batch)
        if not batches:
            return
        await together(*(_upsert_batch(document_id, batch) for batch in batches))


async def query_vectors(query: str, filter: dict = None, top_k: int = 5):
    layout = await offload(_layout)
    document_id = (filter or {}).get('document_id')
    if not document_id:
        raise ValueError('Document-scoped retrieval requires a document_id')
    if layout['mode'] == 'integrated':
        result = await offload(lambda: _index().documents.search(
            namespace=document_id,
            score_by=[{'type': 'embed', 'field': layout['text_field'], 'query': query}],
            top_k=top_k, include_fields=[layout['text_field'], 'document_id', 'chunk_index'], timeout=60,
        ))
    else:
        async with _embedding_slots:
            embedding = await genai.embed_content_async(
                model='models/gemini-embedding-001', content=query, task_type='retrieval_query',
                output_dimensionality=layout['dimension'], request_options={'timeout': 120},
            )
        if layout['mode'] == 'vectors':
            return await offload(lambda: _index().query(
                vector=embedding['embedding'], top_k=top_k, include_metadata=True, filter=filter,
            ))
        result = await offload(lambda: _index().documents.search(
            namespace=document_id,
            score_by=[{'type': 'dense_vector', 'field': layout['vector_field'], 'values': embedding['embedding']}],
            top_k=top_k, include_fields=['text', 'document_id', 'chunk_index'], timeout=60,
        ))
    # Keep the Q&A-facing shape independent of Pinecone's operation family.
    return SimpleNamespace(matches=[
        SimpleNamespace(id=match.id, score=match.score, metadata={
            'text': match.get(layout.get('text_field', 'text'), ''),
            'document_id': match.get('document_id'), 'chunk_index': match.get('chunk_index'),
        }) for match in result.matches
    ])


async def delete_vectors(document_id: str):
    layout = await offload(_layout)
    if layout['mode'] == 'vectors':
        await offload(lambda: _index().delete(filter={'document_id': document_id}))
    else:
        await offload(lambda: _index().documents.delete(namespace=document_id, delete_all=True, timeout=60))
