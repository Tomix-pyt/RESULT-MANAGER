from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class StaffAssignment(TimestampMixin, db.Model):
    __tablename__ = "staff_assignments"
    __table_args__ = (
        db.UniqueConstraint("staff_id", "class_subject_id", "academic_session_id", name="uq_staff_assignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    class_subject_id: Mapped[int] = mapped_column(db.ForeignKey("class_subjects.id"))
    academic_session_id: Mapped[int] = mapped_column(db.ForeignKey("academic_sessions.id"))

    staff: Mapped["User"] = relationship(back_populates="staff_assignments")
    class_subject: Mapped["ClassSubject"] = relationship(back_populates="staff_assignments")
    academic_session: Mapped["AcademicSession"] = relationship(back_populates="staff_assignments")
