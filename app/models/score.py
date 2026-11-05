from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class Score(TimestampMixin, db.Model):
    __tablename__ = "scores"
    __table_args__ = (
        db.UniqueConstraint("student_id", "assessment_component_id", name="uq_student_assessment_score"),
        db.CheckConstraint("score >= 0", name="ck_score_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(db.ForeignKey("students.id"))
    assessment_component_id: Mapped[int] = mapped_column(db.ForeignKey("assessment_components.id"))
    score: Mapped[Decimal] = mapped_column(db.Numeric(6, 2))  # upper bound (max_score) checked in service
    entered_by: Mapped[int] = mapped_column(db.ForeignKey("users.id"))

    student: Mapped["Student"] = relationship(back_populates="scores")
    assessment_component: Mapped["AssessmentComponent"] = relationship(back_populates="scores")
    entered_by_user: Mapped["User"] = relationship(back_populates="scores")
