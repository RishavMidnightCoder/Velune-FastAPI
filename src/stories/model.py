from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.utils.constant import STATUS_DRAFT
from src.utils.db import Base, utcnow


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    genre: Mapped[str] = mapped_column(String(100), default="")
    age_rating: Mapped[str] = mapped_column(String(20), default="All ages")
    description: Mapped[str] = mapped_column(Text, default="")
    cover_image: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default=STATUS_DRAFT, index=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(50), default="Suspenseful")
    languages: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="story",
        cascade="all, delete-orphan",
        order_by="Scene.position",
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    mood: Mapped[str] = mapped_column(String(50), default="Calm")
    narration: Mapped[str] = mapped_column(Text, default="")

    story: Mapped["Story"] = relationship(back_populates="scenes")