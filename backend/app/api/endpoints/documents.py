import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from app.db.prisma import db
from app.core.security import get_current_user
from app.core.redis import redis_client
from app.services.processing import process_document
from app.services.document_text import DOCX_TYPE

router = APIRouter()
logger = logging.getLogger(__name__)


def json_value(value, expected, default):
    # Normalize older rows that stored a JSON string inside a JSON column.
    for _ in range(2):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return default
    return value if isinstance(value, expected) else default


def document_fields(data):
    fields = {
        'topics': json_value(data.topics if data else None, list, []),
        'explanations': json_value(data.explanations if data else None, dict, {}),
        'mindTree': json_value(data.mindTree if data else None, dict, {}),
        'predictedQuestions': json_value(data.predictedQuestions if data else None, list, []),
    }
    fields['topics'] = [topic for topic in fields['topics'] if isinstance(topic, str) and topic.strip()]
    fields['explanations'] = {topic: text for topic, text in fields['explanations'].items() if isinstance(text, str)}
    tree = fields['mindTree']
    if not isinstance(tree.get('name'), str) or not isinstance(tree.get('children'), list):
        fields['mindTree'] = {}
    fields['predictedQuestions'] = [question for question in fields['predictedQuestions'] if isinstance(question, dict) and isinstance(question.get('question'), str) and isinstance(question.get('answer'), str)]
    return fields


async def owned_document(document_id, user, include_data=False):
    document = await db.document.find_unique(
        where={'id': document_id}, include={'documentData': True} if include_data else None,
    )
    if not document:
        raise HTTPException(status_code=404, detail='Document not found')
    if document.userId != user['sub']:
        raise HTTPException(status_code=403, detail='Not authorized to access this document')
    return document


@router.get('/')
async def get_documents(user: dict = Depends(get_current_user)):
    return await db.document.find_many(where={'userId': user['sub']}, order={'createdAt': 'desc'})


@router.get('/{document_id}')
async def get_document_details(document_id: str, user: dict = Depends(get_current_user)):
    cache_key = f'document_details:v2:{document_id}'
    cached = await redis_client.get(cache_key)
    if cached:
        payload = json.loads(cached)
        if payload.get('userId') == user['sub']:
            return payload
    document = await owned_document(document_id, user, include_data=True)
    fields = document_fields(document.documentData)
    progress = int(await redis_client.get(f'progress:{document_id}') or 0)
    error = None
    if document.status == 'failed':
        error = await redis_client.get(f'processing_error:{document_id}') or 'Processing failed. Retry to generate this document’s results.'
    elif document.status == 'ready' and (not fields['topics'] or not fields['mindTree'] or not fields['predictedQuestions']):
        error = 'This document has incomplete results. Retry to regenerate them.'
    payload = {
        'id': document.id, 'name': document.name, 'status': document.status,
        'progress': 100 if document.status == 'ready' else progress,
        'fileUrl': document.fileUrl,
        'fileType': 'docx' if Path(document.name).suffix.lower() == '.docx' else 'pdf',
        'error': error, **fields, 'userId': document.userId,
    }
    if document.status == 'ready' and not error:
        await redis_client.set(cache_key, json.dumps(payload), expire=3600)
    return payload


@router.post('/{document_id}/retry', status_code=202)
async def retry_document(document_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    document = await owned_document(document_id, user, include_data=True)
    fields = document_fields(document.documentData)
    if document.status in ('processing', 'topics_ready', 'deleting'):
        raise HTTPException(status_code=409, detail='This document is already being processed or deleted.')
    if document.status == 'ready' and fields['topics'] and fields['mindTree'] and fields['predictedQuestions']:
        raise HTTPException(status_code=409, detail='This document is already ready.')
    # Claim the existing row atomically so repeated clicks do not enqueue duplicates.
    claimed = await db.document.update_many(
        where={'id': document_id, 'userId': user['sub'], 'status': document.status}, data={'status': 'processing'},
    )
    if not claimed:
        raise HTTPException(status_code=409, detail='The document state changed. Refresh and try again.')
    for key in (f'processing_error:{document_id}', f'document_details:{document_id}', f'document_details:v2:{document_id}'):
        await redis_client.delete(key)
    await redis_client.set(f'progress:{document_id}', '0')
    content_type = DOCX_TYPE if Path(document.name).suffix.lower() == '.docx' else 'application/pdf'
    file_key = document.fileUrl.rsplit('/', 1)[-1]
    background_tasks.add_task(process_document, document.id, document.fileUrl, file_key, content_type)
    return {'id': document.id, 'status': 'processing'}


@router.delete('/{document_id}')
async def delete_document(document_id: str, user: dict = Depends(get_current_user)):
    document = await owned_document(document_id, user)
    if document.status in ('processing', 'topics_ready', 'deleting'):
        raise HTTPException(status_code=409, detail='Wait for processing to finish before deleting this document.')
    claimed = await db.document.update_many(
        where={'id': document_id, 'userId': user['sub'], 'status': document.status}, data={'status': 'deleting'},
    )
    if not claimed:
        raise HTTPException(status_code=409, detail='The document state changed. Refresh and try again.')
    try:
        from app.services.vector_store import delete_vectors
        from app.services.uploadthing_storage import ut_service
        await delete_vectors(document_id)
        if document.fileUrl:
            await ut_service.delete_file(document.fileUrl.rsplit('/', 1)[-1])
        async with db.tx() as transaction:
            await transaction.message.delete_many(where={'documentId': document_id})
            await transaction.documentdata.delete_many(where={'documentId': document_id})
            await transaction.vectormetadata.delete_many(where={'documentId': document_id})
            await transaction.document.delete(where={'id': document_id})
    except Exception:
        logger.exception('Document deletion failed for %s', document_id)
        await db.document.update(where={'id': document_id}, data={'status': 'failed'})
        await redis_client.set(f'processing_error:{document_id}', 'Deletion could not finish. Retry Delete to finish cleaning up this document.', expire=604800)
        raise HTTPException(status_code=503, detail='Deletion could not finish. Please retry Delete.')
    finally:
        for key in (f'document_details:{document_id}', f'document_details:v2:{document_id}'):
            await redis_client.delete(key)
    await redis_client.delete(f'progress:{document_id}')
    await redis_client.delete(f'processing_error:{document_id}')
    return {'message': 'Document deleted successfully'}
