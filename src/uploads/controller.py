import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from src.utils.constant import MAX_UPLOAD_BYTES, UPLOAD_DIR


def _detect_extension(head: bytes) -> str | None:
    """Checks the real file signature instead of trusting the filename or content type."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


async def save_image(file: UploadFile) -> str:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Image must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller")

    extension = _detect_extension(data[:12])
    if extension is None:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, WebP or GIF images are allowed")

    directory = Path(UPLOAD_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{extension}"
    (directory / name).write_bytes(data)
    return f"/uploads/{name}"