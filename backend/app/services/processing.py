from app.db.prisma import db
from app.services.uploadthing_storage import ut_service
from app.services.llm import (
    analysis_context, extract_topics, generate_explanations,
    generate_mind_tree, generate_predicted_questions,
)
from app.services.document_text import extract_to_file, text_chunks
from app.services.parallel import together, offload
from app.services.vector_store import upsert_vectors
from app.core.config import get_settings
from app.core.redis import redis_client
import asyncio
from prisma import Json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

logger = logging.getLogger("uvicorn.error.processing")
_document_slots = asyncio.Semaphore(get_settings().DOCUMENT_CONCURRENCY)


async def _timed(document_id, stage, operation):
    started = perf_counter()
    try:
        return await operation
    finally:
        logger.info("document=%s stage=%s elapsed=%.2fs", document_id, stage, perf_counter() - started)


async def _analyze_document(document_id: str, text_path: str):
    context = await _timed(document_id, "analysis_context", analysis_context(text_path))
    await redis_client.set(f"progress:{document_id}", "30")

    async def topics_and_explanations():
        topics = await extract_topics(context)
        explanations = await generate_explanations(context, topics)
        await _save_document_data(document_id, topics=topics, explanations=explanations)
        await redis_client.set(f"progress:{document_id}", "60")
        await db.document.update(where={"id": document_id}, data={"status": "topics_ready"})

    # Start independent analyses immediately rather than waiting for topics.
    _, mind_tree, questions = await together(
        topics_and_explanations(), generate_mind_tree(context), generate_predicted_questions(context),
    )
    await _update_document_data(document_id, mind_tree=mind_tree, questions=questions)


async def process_document(
    document_id: str, file_url: str, file_key: str,
    content_type: str = "application/pdf", local_path: str = None,
):
    started = perf_counter()
    try:
        # Bound concurrent documents so large uploads cannot exhaust memory/API quota.
        async with _document_slots:
            await db.document.update(where={"id": document_id}, data={"status": "processing"})
            await redis_client.delete(f"document_details:v2:{document_id}")
            await redis_client.delete(f"processing_error:{document_id}")
            with TemporaryDirectory(prefix="synora-process-") as directory:
                source = local_path or str(Path(directory) / "source")
                await redis_client.set(f"progress:{document_id}", "10")
                if not local_path:
                    await ut_service.download_to_file(file_url, source)
                text_path = str(Path(directory) / "text.txt")
                characters = await _timed(document_id, "extract", offload(
                    extract_to_file, source, text_path, content_type,
                ))
                logger.info("document=%s extracted_characters=%s", document_id, characters)
                await redis_client.set(f"progress:{document_id}", "20")
                # Index original text while preparing all document-wide analyses.
                results = await asyncio.gather(
                    _timed(document_id, "analysis", _analyze_document(document_id, text_path)),
                    _timed(document_id, "embeddings", upsert_vectors(document_id, text_chunks(text_path))),
                    return_exceptions=True,
                )
                # Preserve successful analysis if retrieval fails, and vice versa.
                for result in results:
                    if isinstance(result, BaseException):
                        raise result
            await redis_client.set(f"progress:{document_id}", "100")
            await db.document.update(where={"id": document_id}, data={"status": "ready"})
            await redis_client.delete(f"document_details:{document_id}")
            await redis_client.delete(f"document_details:v2:{document_id}")
    except Exception as error:
        logger.exception("Processing failed for document=%s", document_id)
        message = str(error) if isinstance(error, ValueError) and str(error).startswith(("No readable text", "Empty", "Invalid AI", "Document summaries")) else "Document processing failed. Retry to regenerate the missing results."
        await redis_client.set(f"processing_error:{document_id}", message, expire=604800)
        await db.document.update(where={"id": document_id}, data={"status": "failed"})
    finally:
        if local_path:
            Path(local_path).unlink(missing_ok=True)
        logger.info("document=%s stage=total elapsed=%.2fs", document_id, perf_counter() - started)


# ── DB helpers with retry logic ──────────────────────────────

async def _save_document_data(document_id: str, topics: list, explanations: dict = None):
    """Create the DocumentData row with topics and explanations (Phase 1)."""
    if explanations is None:
        explanations = {}
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if not db.is_connected():
                await db.connect()

            fields = {
                "topics": Json(topics), "explanations": Json(explanations),
                "mindTree": Json({}), "predictedQuestions": Json([]),
            }
            await db.documentdata.upsert(
                where={"documentId": document_id},
                data={"create": {
                    "documentId": document_id,
                    **fields,
                }, "update": fields},
            )
            return
        except Exception as e:
            print(f"DB Save (topics) failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise e
            await asyncio.sleep(1)


async def _update_document_data(document_id: str, mind_tree: dict, questions: list):
    """Update the existing DocumentData row with remaining analysis results (Phase 2)."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if not db.is_connected():
                await db.connect()

            await db.documentdata.update(
                where={"documentId": document_id},
                data={
                    "mindTree": Json(mind_tree),
                    "predictedQuestions": Json(questions),
                }
            )
            return
        except Exception as e:
            print(f"DB Update (full analysis) failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise e
            await asyncio.sleep(1)
