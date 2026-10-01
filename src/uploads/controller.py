from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.uploads.model import StoredImage
from src.utils.constant import MAX_UPLOAD_BYTES
from src.utils.db import SessionLocal


def _detect_mime(head: bytes) -> str | None:
    """Checks the real file signature instead of trusting the filename or content type."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_image_bytes(data: bytes) -> str:
    """Stores image bytes in the database and returns the public path, e.g. /uploads/12."""
    mime = _detect_mime(data[:12])
    if mime is None:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, WebP or GIF images are allowed")
    with SessionLocal() as db:
        image = StoredImage(content_type=mime, data=data)
        db.add(image)
        db.commit()
        db.refresh(image)
        return f"/uploads/{image.id}"


async def save_image(file: UploadFile) -> str:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail=f"Image must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller"
        )
    return save_image_bytes(data)


def get_image(db: Session, image_id: int) -> StoredImage:
    image = db.get(StoredImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image