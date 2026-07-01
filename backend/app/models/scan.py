from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Scan(Base):
    __tablename__ = "scans"

    # UUID Primary Key default generated with uuid.uuid4
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Repository URL
    repo_url: Mapped[str] = mapped_column(String, nullable=False)

    # Status of the scan job (pending, running, completed, failed)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")

    # Optional production readiness score out of 100
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optional findings dictionary stored as standard JSON
    findings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Optional webhook callback URL — POSTed to when scan completes
    callback_url: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, default=None
    )

    # Unguessable public share token — safe to expose, never contains secrets
    share_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: secrets.token_hex(32)
    )

    # Progress of the scan (0 to 100)
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # Current step of the scan
    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    # Timestamps with timezone
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Optional link to the user who created this scan (nullable for backwards compat)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    # Relationships
    user: Mapped[Optional[User]] = relationship("User", back_populates="scans")

    def __repr__(self) -> str:
        return f"<Scan(id={self.id}, repo_url='{self.repo_url}', status='{self.status}')>"


# Avoid circular import — User is defined in app.models.user
from app.models.user import User  # noqa: E402
