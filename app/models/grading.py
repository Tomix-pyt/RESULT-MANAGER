from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class GradingScale(TimestampMixin, db.Model):
    __tablename__ = "grading_scales"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120))
    academic_session_id: Mapped[int] = mapped_column(db.ForeignKey("academic_sessions.id"))

    academic_session: Mapped["AcademicSession"] = relationship(back_populates="grading_scales")
    boundaries: Mapped[list["GradeBoundary"]] = relationship(
        back_populates="grading_scale", cascade="all, delete-orphan", order_by="GradeBoundary.min_score.desc()"
    )


class GradeBoundary(TimestampMixin, db.Model):
    __tablename__ = "grade_boundaries"
    __table_args__ = (db.CheckConstraint("min_score <= max_score", name="ck_boundary_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    grading_scale_id: Mapped[int] = mapped_column(db.ForeignKey("grading_scales.id"))
    min_score: Mapped[Decimal] = mapped_column(db.Numeric(6, 2))
    max_score: Mapped[Decimal] = mapped_column(db.Numeric(6, 2))
    grade: Mapped[str] = mapped_column(db.String(5))
    remark: Mapped[Optional[str]] = mapped_column(db.String(80))

    grading_scale: Mapped["GradingScale"] = relationship(back_populates="boundaries")
