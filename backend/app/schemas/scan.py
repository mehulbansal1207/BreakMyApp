from typing import Optional, Any, Dict, List
from uuid import UUID
from datetime import datetime
import re

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
        pattern = r"^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_.-]+\/?$"
        if not re.match(pattern, v.strip()):
            raise ValueError(
                "Invalid GitHub repository URL. Must be a valid HTTPS URL "
                "(e.g., https://github.com/owner/repo)."
            )
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
    """Full scan response — only returned to authenticated scan owner."""
    id: UUID
    repo_url: str
    share_token: str          # safe to expose — used for public share links
    callback_url: Optional[str] = None
    status: str
    score: Optional[int] = None
    findings: Optional[Dict[str, Any]] = None
    progress: Optional[int] = None
    current_step: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScanShareResponse(BaseModel):
    """
    Limited public response returned via share token.
    Never exposes raw findings, secret values, or artifact URLs.
    """
    share_token: str
    repo_url: str
    status: str
    score: Optional[int] = None
    top_priorities: List[Any] = []
    executive_summary: str = ""
    score_explanation: str = ""
    category_summaries: Dict[str, str] = {}
    findings_summary: Dict[str, int] = {}
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanStatus(BaseModel):
    id: UUID
    status: str

    model_config = {"from_attributes": True}
