from sqlalchemy.orm import Mapped, mapped_column
from app.extensions import db
from app.models.base import TimestampMixin


class StudentTrait(TimestampMixin, db.Model):
    """Affective-development or psychomotor rating (1-5) for one student in one term.
    source AUTO = suggested from performance; MANUAL = typed/edited by a person (never overwritten)."""
    __tablename__ = "student_traits"
    __table_args__ = (
        db.UniqueConstraint("enrollment_id", "term_id", "trait_key", name="uq_student_trait"),
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_trait_rating"),
        db.CheckConstraint("source IN ('AUTO','MANUAL')", name="ck_trait_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(db.ForeignKey("student_enrollments.id"))
    term_id: Mapped[int] = mapped_column(db.ForeignKey("terms.id"))
    trait_key: Mapped[str] = mapped_column(db.String(30))
    rating: Mapped[int] = mapped_column(db.Integer)
    source: Mapped[str] = mapped_column(db.String(10), default="AUTO")
