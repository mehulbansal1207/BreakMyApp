import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
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

    def __repr__(self) -> str:
        return f"<Scan(id={self.id}, repo_url='{self.repo_url}', status='{self.status}')>"
