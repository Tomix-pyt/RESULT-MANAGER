from datetime import date, datetime
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin


class Term(TimestampMixin, db.Model):
    __tablename__ = "terms"
    __table_args__ = (db.UniqueConstraint("academic_session_id", "name", name="uq_term_session_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_session_id: Mapped[int] = mapped_column(db.ForeignKey("academic_sessions.id"))
    name: Mapped[str] = mapped_column(db.String(50))  # First Term ...
    start_date: Mapped[Optional[date]] = mapped_column(db.Date)
    end_date: Mapped[Optional[date]] = mapped_column(db.Date)
    is_current: Mapped[bool] = mapped_column(db.Boolean, default=False)
    next_term_begins: Mapped[Optional[date]] = mapped_column(db.Date)
    # Grace period: staff may keep editing submitted scores until this moment.
    edit_deadline: Mapped[Optional[datetime]] = mapped_column(db.DateTime)

    academic_session: Mapped["AcademicSession"] = relationship(back_populates="terms")
    assessment_components: Mapped[list["AssessmentComponent"]] = relationship(back_populates="term")
    results: Mapped[list["Result"]] = relationship(back_populates="term")
