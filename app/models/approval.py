from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db


class ResultApproval(db.Model):
    """Append-only history of workflow actions on a result."""
    __tablename__ = "result_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(db.ForeignKey("results.id"))
    approved_by: Mapped[Optional[int]] = mapped_column(db.ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(db.String(20))
    comment: Mapped[Optional[str]] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, server_default=db.func.now())

    result: Mapped["Result"] = relationship(back_populates="approvals")
    approved_by_user: Mapped[Optional["User"]] = relationship(back_populates="result_approvals")
