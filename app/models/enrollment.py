from typing import Optional
from sqlalchemy import event, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class StudentEnrollment(TimestampMixin, db.Model):
    __tablename__ = "student_enrollments"
    # A student sits in exactly ONE class per academic session. This is enforced by the database
    # (not only by Python checks), so double-clicks, two operators at once, or any future bug
    # cannot create a second enrollment in the same session.
    __table_args__ = (db.UniqueConstraint("student_id", "academic_session_id", name="uq_student_enrollment_session"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(db.ForeignKey("students.id"))
    class_session_id: Mapped[int] = mapped_column(db.ForeignKey("class_sessions.id"))
    # Copy of class_session.academic_session_id. Filled automatically (see the listener below);
    # it exists so the database can enforce "one class per session".
    academic_session_id: Mapped[int] = mapped_column(db.ForeignKey("academic_sessions.id"))
    roll_number: Mapped[Optional[int]] = mapped_column(db.Integer)

    student: Mapped["Student"] = relationship(back_populates="enrollments")
    class_session: Mapped["ClassSession"] = relationship(back_populates="student_enrollments")
    # Which subjects THIS student takes. Defaults come from the class; the
    # operator can add or remove individual rows.
    subjects: Mapped[list["StudentSubject"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )
    term_reports: Mapped[list["StudentTermReport"]] = relationship(cascade="all, delete-orphan")
    traits: Mapped[list["StudentTrait"]] = relationship(cascade="all, delete-orphan")


class StudentSubject(TimestampMixin, db.Model):
    __tablename__ = "student_subjects"
    __table_args__ = (db.UniqueConstraint("enrollment_id", "class_subject_id", name="uq_student_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(db.ForeignKey("student_enrollments.id"))
    class_subject_id: Mapped[int] = mapped_column(db.ForeignKey("class_subjects.id"))

    enrollment: Mapped["StudentEnrollment"] = relationship(back_populates="subjects")
    class_subject: Mapped["ClassSubject"] = relationship(back_populates="student_subjects")


@event.listens_for(StudentEnrollment, "before_insert")
@event.listens_for(StudentEnrollment, "before_update")
def _sync_academic_session(mapper, connection, target):
    """Keep academic_session_id equal to the class session's session, whatever code changed the row."""
    from app.models.class_session import ClassSession
    target.academic_session_id = connection.scalar(
        select(ClassSession.academic_session_id).where(ClassSession.id == target.class_session_id)
    )
