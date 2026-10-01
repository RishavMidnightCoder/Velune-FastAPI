from datetime import datetime
from typing import Literal

from pydantic import Field

from src.utils.helper import CamelModel


class SceneDto(CamelModel):
    title: str = Field(default="", max_length=200)
    mood: str = Field(default="Calm", max_length=50)
    narration: str = ""


class StoryDto(CamelModel):
    """Used for both create and update (PUT replaces the whole story)."""

    title: str = Field(min_length=1, max_length=200)
    genre: str = Field(default="", max_length=100)
    age_rating: str = Field(default="All ages", max_length=20)
    description: str = ""
    cover_image: str = Field(default="", max_length=500)
    status: Literal["draft", "published"] = "draft"
    system_prompt: str = ""
    tone: str = Field(default="Suspenseful", max_length=50)
    languages: list[str] = Field(default_factory=lambda: ["English"])
    scenes: list[SceneDto] = Field(default_factory=list)


class StoryAdminOut(StoryDto):
    id: int
    created_at: datetime
    updated_at: datetime


class StoryAdminRow(CamelModel):
    id: int
    title: str
    genre: str
    age_rating: str
    status: str
    scenes: int
    players: int
    updated_at: datetime


class StoryPublicOut(CamelModel):
    """What players see. The system prompt is never exposed here."""

    id: int
    title: str
    genre: str
    age_rating: str
    description: str
    cover_image: str
    languages: list[str]
    scene_count: int


class DashboardStatsOut(CamelModel):
    total_stories: int
    published_stories: int
    total_users: int
    new_users_week: int
    active_players_week: int
    messages_today: int