from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(db.String(50))
    entity_type: Mapped[Optional[str]] = mapped_column(db.String(50))
    entity_id: Mapped[Optional[int]] = mapped_column(db.Integer)
    description: Mapped[Optional[str]] = mapped_column(db.Text)
    ip_address: Mapped[Optional[str]] = mapped_column(db.String(45))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, server_default=db.func.now())

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")
