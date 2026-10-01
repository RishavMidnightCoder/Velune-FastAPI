from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.stories import controller
from src.stories.dtos import (
    DashboardStatsOut,
    StoryAdminOut,
    StoryAdminRow,
    StoryDto,
    StoryPublicOut,
)
from src.utils.db import get_db
from src.utils.helper import require_admin

# Public
router = APIRouter(prefix="/stories", tags=["Stories"])

# Admin
admin_router = APIRouter(
    prefix="/admin/stories", tags=["Admin · Stories"], dependencies=[Depends(require_admin)]
)
stats_router = APIRouter(
    prefix="/admin/stats", tags=["Admin · Stats"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[StoryPublicOut])
def list_stories(db: Session = Depends(get_db)):
    return controller.list_public_stories(db)


@router.get("/{story_id}", response_model=StoryPublicOut)
def get_story(story_id: int, db: Session = Depends(get_db)):
    return controller.get_public_story(db, story_id)


@admin_router.get("", response_model=list[StoryAdminRow])
def admin_list(db: Session = Depends(get_db)):
    return controller.list_admin_stories(db)


@admin_router.post("", response_model=StoryAdminOut, status_code=201)
def admin_create(dto: StoryDto, db: Session = Depends(get_db)):
    return controller.create_story(db, dto)


@admin_router.get("/{story_id}", response_model=StoryAdminOut)
def admin_get(story_id: int, db: Session = Depends(get_db)):
    return controller.get_admin_story(db, story_id)


@admin_router.put("/{story_id}", response_model=StoryAdminOut)
def admin_update(story_id: int, dto: StoryDto, db: Session = Depends(get_db)):
    return controller.update_story(db, story_id, dto)


@admin_router.delete("/{story_id}", status_code=204)
def admin_delete(story_id: int, db: Session = Depends(get_db)):
    controller.delete_story(db, story_id)
    return Response(status_code=204)


@stats_router.get("", response_model=DashboardStatsOut)
def stats(db: Session = Depends(get_db)):
    return controller.dashboard_stats(db)