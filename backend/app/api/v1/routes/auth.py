from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Returns the currently authenticated user's info."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "firebase_uid": current_user.firebase_uid,
        "created_at": current_user.created_at.isoformat(),
        "is_active": current_user.is_active,
    }
