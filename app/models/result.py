from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin

RESULT_STATUSES = ("DRAFT", "SUBMITTED", "REVIEWED", "APPROVED", "REJECTED", "REOPENED", "LOCKED", "PUBLISHED")


class Result(TimestampMixin, db.Model):
    __tablename__ = "results"
    __table_args__ = (
        db.UniqueConstraint("student_id", "class_subject_id", "term_id", name="uq_student_result"),
        db.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','REVIEWED','APPROVED','REJECTED','REOPENED','LOCKED','PUBLISHED')",
            name="ck_result_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(db.ForeignKey("students.id"))
    class_subject_id: Mapped[int] = mapped_column(db.ForeignKey("class_subjects.id"))
    term_id: Mapped[int] = mapped_column(db.ForeignKey("terms.id"))
    total_score: Mapped[Optional[Decimal]] = mapped_column(db.Numeric(6, 2))
    grade: Mapped[Optional[str]] = mapped_column(db.String(5))
    remark: Mapped[Optional[str]] = mapped_column(db.String(80))
    position: Mapped[Optional[int]] = mapped_column(db.Integer)
    class_highest: Mapped[Optional[Decimal]] = mapped_column(db.Numeric(6, 2))   # highest total in this subject, this class, this term
    class_lowest: Mapped[Optional[Decimal]] = mapped_column(db.Numeric(6, 2))
    status: Mapped[str] = mapped_column(db.String(20), default="DRAFT")

    student: Mapped["Student"] = relationship(back_populates="results")
    class_subject: Mapped["ClassSubject"] = relationship(back_populates="results")
    term: Mapped["Term"] = relationship(back_populates="results")
    approvals: Mapped[list["ResultApproval"]] = relationship(back_populates="result", cascade="all, delete-orphan")
