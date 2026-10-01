from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from src.utils.db import Base, utcnow


class StoredImage(Base):
    __tablename__ = "stored_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_type: Mapped[str] = mapped_column(String(50))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)