from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class Class(TimestampMixin, db.Model):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(50), unique=True)  # "JSS 1 A"
    level: Mapped[Optional[str]] = mapped_column(db.String(20))    # "JSS 1"
    arm: Mapped[Optional[str]] = mapped_column(db.String(20))      # "A"
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True)

    class_sessions: Mapped[list["ClassSession"]] = relationship(back_populates="class_")
