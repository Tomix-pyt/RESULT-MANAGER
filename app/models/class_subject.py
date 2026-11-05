from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class ClassSubject(TimestampMixin, db.Model):
    __tablename__ = "class_subjects"
    __table_args__ = (db.UniqueConstraint("class_session_id", "subject_id", name="uq_class_session_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    class_session_id: Mapped[int] = mapped_column(db.ForeignKey("class_sessions.id"))
    subject_id: Mapped[int] = mapped_column(db.ForeignKey("subjects.id"))

    class_session: Mapped["ClassSession"] = relationship(back_populates="class_subjects")
    subject: Mapped["Subject"] = relationship(back_populates="class_subjects")
    staff_assignments: Mapped[list["StaffAssignment"]] = relationship(back_populates="class_subject")
    assessment_components: Mapped[list["AssessmentComponent"]] = relationship(back_populates="class_subject")
    results: Mapped[list["Result"]] = relationship(back_populates="class_subject")
    student_subjects: Mapped[list["StudentSubject"]] = relationship(back_populates="class_subject")
