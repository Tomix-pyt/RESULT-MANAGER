from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import TimestampMixin

ROLES = ("OPERATOR", "STAFF")


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (db.CheckConstraint("role IN ('OPERATOR','STAFF')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(db.String(80), unique=True)
    email: Mapped[Optional[str]] = mapped_column(db.String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(db.String(255))
    first_name: Mapped[str] = mapped_column(db.String(80))
    last_name: Mapped[str] = mapped_column(db.String(80))
    role: Mapped[str] = mapped_column(db.String(20), default="STAFF")
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True)

    staff_assignments: Mapped[list["StaffAssignment"]] = relationship(back_populates="staff")
    scores: Mapped[list["Score"]] = relationship(back_populates="entered_by_user")
    result_approvals: Mapped[list["ResultApproval"]] = relationship(back_populates="approved_by_user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_operator(self) -> bool:
        return self.role == "OPERATOR"
