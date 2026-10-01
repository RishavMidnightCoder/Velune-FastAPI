from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.characters import controller
from src.characters.dtos import CharacterDto, CharacterOut
from src.utils.db import get_db
from src.utils.helper import require_admin

router = APIRouter(prefix="/characters", tags=["Characters"])
admin_router = APIRouter(
    prefix="/admin/characters", tags=["Admin · Characters"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[CharacterOut])
def list_public(db: Session = Depends(get_db)):
    return controller.list_characters(db, published_only=True)


@admin_router.get("", response_model=list[CharacterOut])
def admin_list(db: Session = Depends(get_db)):
    return controller.list_characters(db)


@admin_router.post("", response_model=CharacterOut, status_code=201)
def admin_create(dto: CharacterDto, db: Session = Depends(get_db)):
    return controller.create_character(db, dto)


@admin_router.put("/{character_id}", response_model=CharacterOut)
def admin_update(character_id: int, dto: CharacterDto, db: Session = Depends(get_db)):
    return controller.update_character(db, character_id, dto)


@admin_router.delete("/{character_id}", status_code=204)
def admin_delete(character_id: int, db: Session = Depends(get_db)):
    controller.delete_character(db, character_id)
    return Response(status_code=204)