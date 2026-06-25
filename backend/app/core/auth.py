import json
import os
from typing import Optional

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User

# ---------------------------------------------------------------------------
# Initialize Firebase Admin SDK once at module level.
# Supports two methods:
# 1. FIREBASE_SERVICE_ACCOUNT_JSON_FILE — path to JSON file (local dev)
# 2. FIREBASE_SERVICE_ACCOUNT_JSON — raw JSON string (Railway/production)
# ---------------------------------------------------------------------------
_service_account_file = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON_FILE", "")
_service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")

if not firebase_admin._apps:
    if _service_account_file and os.path.exists(_service_account_file):
        firebase_admin.initialize_app(credentials.Certificate(_service_account_file))
    elif _service_account_json:
        _service_account_dict = json.loads(_service_account_json)
        firebase_admin.initialize_app(credentials.Certificate(_service_account_dict))


async def get_current_user(
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header. Expected: Bearer <token>",
        )

    token = authorization.removeprefix("Bearer ")

    try:
        decoded_token = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    firebase_uid: str = decoded_token["uid"]
    # GitHub users with a private primary email may have no "email" claim.
    # Fall back to the identities array, then a deterministic placeholder so
    # the NOT NULL / UNIQUE constraint on User.email is never violated.
    email: str | None = decoded_token.get("email")
    if not email:
        identities = decoded_token.get("firebase", {}).get("identities", {})
        emails: list = identities.get("email", [])
        email = emails[0] if emails else f"{firebase_uid}@no-email.firebase.local"

    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(firebase_uid=firebase_uid, email=email)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif user.email != email and email:
        user.email = email
        await db.commit()
        await db.refresh(user)

    return user


async def get_optional_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if authorization is None:
        return None
    try:
        return await get_current_user(authorization=authorization, db=db)
    except Exception:
        return None