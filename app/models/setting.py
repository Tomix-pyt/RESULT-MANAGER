from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from app.extensions import db


class Setting(db.Model):
    """Key/value store for school-wide editables (name, principal's remark, signature text, next-term date...)."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(db.String(80), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(db.Text)
