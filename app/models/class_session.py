from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class ClassSession(TimestampMixin, db.Model):
    __tablename__ = "class_sessions"
    __table_args__ = (db.UniqueConstraint("class_id", "academic_session_id", name="uq_class_session"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(db.ForeignKey("classes.id"))
    academic_session_id: Mapped[int] = mapped_column(db.ForeignKey("academic_sessions.id"))
    form_teacher_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("users.id"))

    form_teacher: Mapped[Optional["User"]] = relationship(foreign_keys=[form_teacher_id])
    class_: Mapped["Class"] = relationship(back_populates="class_sessions")
    academic_session: Mapped["AcademicSession"] = relationship(back_populates="class_sessions")
    student_enrollments: Mapped[list["StudentEnrollment"]] = relationship(back_populates="class_session")
    class_subjects: Mapped[list["ClassSubject"]] = relationship(back_populates="class_session")
