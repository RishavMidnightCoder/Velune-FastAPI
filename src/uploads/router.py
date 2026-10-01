from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from src.uploads import controller
from src.uploads.dtos import UploadOut
from src.utils.db import get_db
from src.utils.helper import require_admin

# Admin: upload an image
router = APIRouter(prefix="/admin/uploads", tags=["Admin · Uploads"], dependencies=[Depends(require_admin)])

# Public: serve a stored image (used by <img> tags)
media_router = APIRouter(prefix="/uploads", tags=["Media"])


@router.post("", response_model=UploadOut, status_code=201)
async def upload_image(file: UploadFile = File(...)):
    return UploadOut(url=await controller.save_image(file))


@media_router.get("/{image_id}")
def serve_image(image_id: int, db: Session = Depends(get_db)):
    image = controller.get_image(db, image_id)
    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )