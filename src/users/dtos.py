from datetime import datetime

from pydantic import EmailStr, Field

from src.utils.helper import CamelModel


class SignupDto(CamelModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)


class LoginDto(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=64)


class UserOut(CamelModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime


class TokenOut(CamelModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AdminUserOut(UserOut):
    stories_played: int = 0