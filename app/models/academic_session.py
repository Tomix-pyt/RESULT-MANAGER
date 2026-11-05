from datetime import date
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class AcademicSession(TimestampMixin, db.Model):
    __tablename__ = "academic_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(20), unique=True)  # 2026/2027
    start_date: Mapped[Optional[date]] = mapped_column(db.Date)
    end_date: Mapped[Optional[date]] = mapped_column(db.Date)
    is_current: Mapped[bool] = mapped_column(db.Boolean, default=False)

    terms: Mapped[list["Term"]] = relationship(back_populates="academic_session", cascade="all, delete-orphan")
    class_sessions: Mapped[list["ClassSession"]] = relationship(back_populates="academic_session")
    staff_assignments: Mapped[list["StaffAssignment"]] = relationship(back_populates="academic_session")
    grading_scales: Mapped[list["GradingScale"]] = relationship(back_populates="academic_session")
