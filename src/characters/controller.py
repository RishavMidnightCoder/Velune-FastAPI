from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.characters.dtos import CharacterDto, CharacterOut
from src.characters.model import Character
from src.stories.model import Story
from src.utils.constant import STATUS_PUBLISHED


def _out(c: Character, story_title: str) -> CharacterOut:
    return CharacterOut(
        id=c.id,
        story_id=c.story_id,
        story=story_title,
        name=c.name,
        role=c.role,
        personality=c.personality,
        backstory=c.backstory,
    )


def list_characters(db: Session, published_only: bool = False) -> list[CharacterOut]:
    stmt = select(Character, Story.title).join(Story, Story.id == Character.story_id)
    if published_only:
        stmt = stmt.where(Story.status == STATUS_PUBLISHED)
    rows = db.execute(stmt.order_by(Character.id.desc())).all()
    return [_out(c, title) for c, title in rows]


def _story_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _character_or_404(db: Session, character_id: int) -> Character:
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


def create_character(db: Session, dto: CharacterDto) -> CharacterOut:
    story = _story_or_404(db, dto.story_id)
    character = Character(
        story_id=dto.story_id,
        name=dto.name.strip(),
        role=dto.role,
        personality=dto.personality,
        backstory=dto.backstory,
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return _out(character, story.title)


def update_character(db: Session, character_id: int, dto: CharacterDto) -> CharacterOut:
    character = _character_or_404(db, character_id)
    story = _story_or_404(db, dto.story_id)
    character.story_id = dto.story_id
    character.name = dto.name.strip()
    character.role = dto.role
    character.personality = dto.personality
    character.backstory = dto.backstory
    db.commit()
    db.refresh(character)
    return _out(character, story.title)


def delete_character(db: Session, character_id: int) -> None:
    character = _character_or_404(db, character_id)
    db.delete(character)
    db.commit()