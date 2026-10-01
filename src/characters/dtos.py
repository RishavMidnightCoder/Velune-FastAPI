from pydantic import Field

from src.utils.helper import CamelModel


class CharacterDto(CamelModel):
    story_id: int
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="", max_length=100)
    personality: str = ""
    backstory: str = ""


class CharacterOut(CamelModel):
    id: int
    story_id: int
    story: str
    name: str
    role: str
    personality: str
    backstory: str