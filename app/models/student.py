from datetime import date
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin

STUDENT_STATUSES = ("ACTIVE", "INACTIVE", "GRADUATED", "TRANSFERRED", "WITHDRAWN")


class Student(TimestampMixin, db.Model):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    admission_number: Mapped[str] = mapped_column(db.String(50), unique=True)  # persistent, never reused
    first_name: Mapped[str] = mapped_column(db.String(80))
    middle_name: Mapped[Optional[str]] = mapped_column(db.String(80))
    last_name: Mapped[str] = mapped_column(db.String(80))
    gender: Mapped[Optional[str]] = mapped_column(db.String(10))
    date_of_birth: Mapped[Optional[date]] = mapped_column(db.Date)
    status: Mapped[str] = mapped_column(db.String(20), default="ACTIVE")

    enrollments: Mapped[list["StudentEnrollment"]] = relationship(back_populates="student")
    scores: Mapped[list["Score"]] = relationship(back_populates="student")
    results: Mapped[list["Result"]] = relationship(back_populates="student")

    @property
    def full_name(self) -> str:
        parts = [self.last_name.upper(), self.first_name, self.middle_name or ""]
        return " ".join(p for p in parts if p)
