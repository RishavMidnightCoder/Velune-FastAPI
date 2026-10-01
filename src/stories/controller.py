from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from src.play.model import ChatMessage, UserProgress
from src.stories.dtos import (
    DashboardStatsOut,
    StoryAdminOut,
    StoryAdminRow,
    StoryDto,
    StoryPublicOut,
)
from src.stories.model import Scene, Story
from src.users.model import User
from src.utils.constant import STATUS_PUBLISHED
from src.utils.db import utcnow


def _get_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


def _validate_publishable(dto: StoryDto) -> None:
    if dto.status != STATUS_PUBLISHED:
        return
    if not dto.scenes:
        raise HTTPException(status_code=400, detail="Add at least one scene before publishing")
    if any(not s.title.strip() for s in dto.scenes):
        raise HTTPException(status_code=400, detail="Every scene needs a title before publishing")


def _apply(story: Story, dto: StoryDto) -> None:
    story.title = dto.title.strip()
    story.genre = dto.genre
    story.age_rating = dto.age_rating
    story.description = dto.description
    story.cover_image = dto.cover_image
    story.status = dto.status
    story.system_prompt = dto.system_prompt
    story.tone = dto.tone
    story.languages = dto.languages
    story.updated_at = utcnow()
    story.scenes = [
        Scene(position=i, title=s.title.strip(), mood=s.mood, narration=s.narration)
        for i, s in enumerate(dto.scenes)
    ]


# ---------- Admin ----------
def list_admin_stories(db: Session) -> list[StoryAdminRow]:
    players = dict(
        db.execute(
            select(UserProgress.story_id, func.count(UserProgress.id)).group_by(UserProgress.story_id)
        ).all()
    )
    stories = db.scalars(select(Story).order_by(Story.updated_at.desc())).all()
    return [
        StoryAdminRow(
            id=s.id,
            title=s.title,
            genre=s.genre,
            age_rating=s.age_rating,
            status=s.status,
            scenes=len(s.scenes),
            players=players.get(s.id, 0),
            updated_at=s.updated_at,
        )
        for s in stories
    ]


def get_admin_story(db: Session, story_id: int) -> StoryAdminOut:
    return StoryAdminOut.model_validate(_get_or_404(db, story_id))


def create_story(db: Session, dto: StoryDto) -> StoryAdminOut:
    _validate_publishable(dto)
    story = Story()
    _apply(story, dto)
    db.add(story)
    db.commit()
    db.refresh(story)
    return StoryAdminOut.model_validate(story)


def update_story(db: Session, story_id: int, dto: StoryDto) -> StoryAdminOut:
    _validate_publishable(dto)
    story = _get_or_404(db, story_id)
    _apply(story, dto)
    db.commit()
    db.refresh(story)
    return StoryAdminOut.model_validate(story)


def delete_story(db: Session, story_id: int) -> None:
    story = _get_or_404(db, story_id)
    db.delete(story)
    db.commit()


def dashboard_stats(db: Session) -> DashboardStatsOut:
    now = utcnow()
    week_ago = now - timedelta(days=7)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return DashboardStatsOut(
        total_stories=db.scalar(select(func.count(Story.id))) or 0,
        published_stories=db.scalar(
            select(func.count(Story.id)).where(Story.status == STATUS_PUBLISHED)
        ) or 0,
        total_users=db.scalar(select(func.count(User.id))) or 0,
        new_users_week=db.scalar(select(func.count(User.id)).where(User.created_at >= week_ago)) or 0,
        active_players_week=db.scalar(
            select(func.count(distinct(ChatMessage.user_id))).where(ChatMessage.created_at >= week_ago)
        ) or 0,
        messages_today=db.scalar(
            select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= start_of_day)
        ) or 0,
    )


# ---------- Public (published only) ----------
def list_public_stories(db: Session) -> list[StoryPublicOut]:
    stories = db.scalars(
        select(Story).where(Story.status == STATUS_PUBLISHED).order_by(Story.updated_at.desc())
    ).all()
    return [_public(s) for s in stories]


def get_public_story(db: Session, story_id: int) -> StoryPublicOut:
    story = db.get(Story, story_id)
    if story is None or story.status != STATUS_PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    return _public(story)


def _public(s: Story) -> StoryPublicOut:
    return StoryPublicOut(
        id=s.id,
        title=s.title,
        genre=s.genre,
        age_rating=s.age_rating,
        description=s.description,
        cover_image=s.cover_image,
        languages=s.languages or [],
        scene_count=len(s.scenes),
    )