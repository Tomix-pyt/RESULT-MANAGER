from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from app.extensions import db


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(db.DateTime, server_default=db.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )
