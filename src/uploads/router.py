from fastapi import APIRouter, Depends, File, UploadFile

from src.uploads import controller
from src.uploads.dtos import UploadOut
from src.utils.helper import require_admin

router = APIRouter(prefix="/admin/uploads", tags=["Admin · Uploads"], dependencies=[Depends(require_admin)])


@router.post("", response_model=UploadOut, status_code=201)
async def upload_image(file: UploadFile = File(...)):
    return UploadOut(url=await controller.save_image(file))