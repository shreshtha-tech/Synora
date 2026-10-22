import asyncio
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
import uuid

from fastapi import APIRouter, UploadFile, File, Depends, BackgroundTasks, HTTPException
from app.core.config import get_settings
from app.core.security import get_current_user
from app.services.uploadthing_storage import ut_service
from app.db.prisma import db
from app.services.processing import process_document
from app.services.document_text import DOCX_TYPE

router = APIRouter()
logger = logging.getLogger(__name__)


async def _spool_upload(file: UploadFile, destination: str, limit: int) -> int:
    size = 0
    with open(destination, "wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(status_code=413, detail=f"File exceeds the {limit // (1024 * 1024)} MB upload limit.")
            await asyncio.to_thread(output.write, chunk)
    if not size:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    return size


@router.post("/")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if file.content_type not in ("application/pdf", DOCX_TYPE):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF and DOCX are supported.")

    extension = "pdf" if file.content_type == "application/pdf" else "docx"
    filename = f"{user['sub']}_{uuid.uuid4()}.{extension}"
    with NamedTemporaryFile(prefix="synora-upload-", suffix=f".{extension}", delete=False) as temporary:
        local_path = temporary.name
    handed_off = False
    try:
        size = await _spool_upload(file, local_path, get_settings().MAX_UPLOAD_MB * 1024 * 1024)
        # Upload the full original file from disk. Never discard pages.
        try:
            with open(local_path, "rb") as source:
                result = await ut_service.upload_file(source, filename, file.content_type, file_size=size)
        except Exception:
            logger.exception("File storage upload failed")
            raise HTTPException(status_code=502, detail="File storage is unavailable. Please retry your upload.")

        try:
            doc = await db.document.create(data={
                "userId": user['sub'], "name": file.filename or filename,
                "fileUrl": result["url"], "status": "processing",
            })
        except Exception:
            logger.exception("Document creation failed after storage upload")
            try:
                await ut_service.delete_file(result["key"])
            except Exception:
                logger.exception("Unable to clean up unrecorded uploaded file")
            raise HTTPException(status_code=503, detail="Unable to save your document. Please retry.")

        # Reuse the local original, avoiding a second full network download.
        background_tasks.add_task(
            process_document, doc.id, result["url"], result["key"], file.content_type, local_path,
        )
        handed_off = True
        return {"id": doc.id, "status": "processing", "message": "File uploaded and processing started"}
    finally:
        if not handed_off:
            Path(local_path).unlink(missing_ok=True)
