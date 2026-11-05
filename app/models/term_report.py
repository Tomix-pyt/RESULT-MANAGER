from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from app.extensions import db
from app.models.base import TimestampMixin


class StudentTermReport(TimestampMixin, db.Model):
    """One row per student per term: overall figures + the two teacher remarks printed on the result."""
    __tablename__ = "student_term_reports"
    __table_args__ = (db.UniqueConstraint("enrollment_id", "term_id", name="uq_term_report"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(db.ForeignKey("student_enrollments.id"))
    term_id: Mapped[int] = mapped_column(db.ForeignKey("terms.id"))
    total_obtained: Mapped[Optional[Decimal]] = mapped_column(db.Numeric(8, 2))
    total_obtainable: Mapped[Optional[Decimal]] = mapped_column(db.Numeric(8, 2))
    average: Mapped[Optional[Decimal]] = mapped_column(db.Numeric(6, 2))
    position: Mapped[Optional[int]] = mapped_column(db.Integer)
    class_size: Mapped[Optional[int]] = mapped_column(db.Integer)
    form_teacher_remark: Mapped[Optional[str]] = mapped_column(db.Text)
    principal_remark: Mapped[Optional[str]] = mapped_column(db.Text)
