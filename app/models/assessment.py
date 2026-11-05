from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class AssessmentComponent(TimestampMixin, db.Model):
    __tablename__ = "assessment_components"
    __table_args__ = (
        db.UniqueConstraint("class_subject_id", "term_id", "name", name="uq_assessment_component"),
        db.CheckConstraint("max_score > 0", name="ck_assessment_max_positive"),
        db.CheckConstraint("weight > 0", name="ck_assessment_weight_positive"),
        db.CheckConstraint("report_slot IS NULL OR report_slot BETWEEN 1 AND 4", name="ck_assessment_report_slot"),
        db.UniqueConstraint("class_subject_id", "term_id", "report_slot", name="uq_assessment_report_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_subject_id: Mapped[int] = mapped_column(db.ForeignKey("class_subjects.id"))
    term_id: Mapped[int] = mapped_column(db.ForeignKey("terms.id"))
    name: Mapped[str] = mapped_column(db.String(80))  # CA 1, Exam ...
    code: Mapped[Optional[str]] = mapped_column(db.String(20))
    max_score: Mapped[int] = mapped_column(db.Integer)
    weight: Mapped[int] = mapped_column(db.Integer)
    position: Mapped[Optional[int]] = mapped_column(db.Integer)  # display order
    # Which column of the printed result this fills: 1=1'st CA, 2=2'nd CA, 3=3'rd CA, 4=Exams
    report_slot: Mapped[Optional[int]] = mapped_column(db.Integer)

    class_subject: Mapped["ClassSubject"] = relationship(back_populates="assessment_components")
    term: Mapped["Term"] = relationship(back_populates="assessment_components")
    scores: Mapped[list["Score"]] = relationship(back_populates="assessment_component")
