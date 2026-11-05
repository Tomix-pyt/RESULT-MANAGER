from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class Subject(TimestampMixin, db.Model):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(db.String(20), unique=True)
    name: Mapped[str] = mapped_column(db.String(120))
    description: Mapped[Optional[str]] = mapped_column(db.Text)
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True)

    class_subjects: Mapped[list["ClassSubject"]] = relationship(back_populates="subject")
