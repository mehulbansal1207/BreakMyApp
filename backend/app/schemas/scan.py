import re
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

class ScanCreate(BaseModel):
    repo_url: str = Field(..., description="The GitHub repository URL to scan.")
    callback_url: Optional[str] = Field(
        default=None,
        description="Optional URL to POST scan results to when complete."
    )

    @field_validator("repo_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        # Check if URL matches a valid GitHub repo format
        pattern = r"^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_.-]+\/?$"
        if not re.match(pattern, v.strip()):
            raise ValueError("Invalid GitHub repository URL. Must be a valid HTTPS URL (e.g., https://github.com/owner/repo).")
        return v.strip()

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("callback_url must be a valid HTTP or HTTPS URL.")
        return v

class ScanResponse(BaseModel):
    id: UUID
    repo_url: str
    callback_url: Optional[str] = None
    status: str
    score: Optional[int] = None
    findings: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class ScanStatus(BaseModel):
    id: UUID
    status: str

    model_config = {
        "from_attributes": True
    }
