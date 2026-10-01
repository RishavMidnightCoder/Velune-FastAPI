from datetime import datetime

from pydantic import Field

from src.utils.helper import CamelModel


class ActionDto(CamelModel):
    action: str = Field(min_length=1, max_length=1000)
    language: str = "English"


class SceneUpdateDto(CamelModel):
    scene_index: int = Field(ge=0)


class MessageOut(CamelModel):
    id: int
    role: str
    content: str
    created_at: datetime


class SceneBrief(CamelModel):
    index: int
    title: str
    mood: str


class CurrentScene(SceneBrief):
    narration: str


class CharacterBrief(CamelModel):
    name: str
    role: str


class PlayStateOut(CamelModel):
    story_id: int
    title: str
    languages: list[str]
    scenes: list[SceneBrief]
    current_scene_index: int
    current_scene: CurrentScene
    characters: list[CharacterBrief]
    messages: list[MessageOut]
    memory_journal: str
    progress: int


class ProgressCardOut(CamelModel):
    story_id: int
    title: str
    genre: str
    cover_image: str
    scene_index: int
    progress: int