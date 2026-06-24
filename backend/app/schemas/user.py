from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class UserResponse(BaseModel):
    id: UUID
    email: str
    firebase_uid: str
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}
