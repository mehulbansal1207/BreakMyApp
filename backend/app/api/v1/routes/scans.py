from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.limiter import check_rate_limit
from app.core.auth import get_current_user, get_optional_user
from app.models.scan import Scan
from app.models.user import User
from app.schemas.scan import ScanCreate, ScanResponse, ScanShareResponse
from app.tasks.analysis import run_analysis
from app.services.minio_service import get_artifact_urls

router = APIRouter(prefix="/scans", tags=["scans"])


def _build_share_response(scan: Scan) -> ScanShareResponse:
    """Build a safe limited public response from a scan — no secrets, no artifacts."""
    findings: dict = scan.findings or {}
    ai: dict = findings.get("ai_explanation") or {}
    cat_exp: dict = ai.get("category_summaries") or {}

    return ScanShareResponse(
        share_token=scan.share_token,
        repo_url=scan.repo_url,
        status=scan.status,
        score=scan.score,
        top_priorities=ai.get("top_priorities", [])[:3],
        executive_summary=ai.get("executive_summary", ""),
        score_explanation=ai.get("score_explanation", ""),
        category_summaries={
            k: v for k, v in cat_exp.items()
            if k in ("secrets", "security", "code_quality", "dependencies", "custom")
        },
        findings_summary={
            "secrets": findings.get("secrets", {}).get("findings_count", 0),
            "security": findings.get("semgrep", {}).get("findings_count", 0),
            "code_quality": findings.get("bandit", {}).get("findings_count", 0),
            "dependencies": findings.get("dependencies", {}).get("findings_count", 0),
            "custom": findings.get("custom", {}).get("findings_count", 0),
        },
        created_at=scan.created_at,
    )


@router.post("/", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(
    request: Request,
    scan_in: ScanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(ip)

    new_scan = Scan(
        repo_url=scan_in.repo_url,
        status="pending",
        callback_url=scan_in.callback_url,
    )

    if current_user is not None:
        new_scan.user_id = current_user.id

    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    run_analysis.delay(str(new_scan.id))

    return new_scan


@router.get("/", response_model=list[ScanResponse])
async def list_scans(
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    if current_user is None:
        return []

    result = await db.execute(
        select(Scan)
        .where(Scan.user_id == current_user.id)
        .order_by(Scan.created_at.desc())
        .limit(limit)
    )
    scans = result.scalars().all()
    return scans


@router.get("/share/{share_token}", response_model=ScanShareResponse)
async def get_scan_by_share_token(
    share_token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint — returns limited scan data via share token.
    Never exposes raw findings, secret values, or artifact URLs.
    """
    result = await db.execute(
        select(Scan).where(Scan.share_token == share_token)
    )
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found.",
        )

    return _build_share_response(scan)


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full scan data — requires authentication.
    Only the scan owner can access their scan.
    Anonymous scans (user_id=None) are accessible only via share token.
    """
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID '{scan_id}' not found.",
        )

    if scan.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this scan.",
        )

    return scan


@router.get("/{scan_id}/summary")
async def get_scan_summary(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lightweight summary for GitHub Action. Requires authentication.
    """
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID '{scan_id}' not found.",
        )

    if scan.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this scan.",
        )

    if scan.status != "completed":
        return {
            "status": scan.status,
            "message": "Scan is not yet complete",
            "score": None,
        }

    findings = scan.findings or {}
    ai = findings.get("ai_explanation", {})

    return {
        "status": "completed",
        "score": scan.score,
        "repo_url": scan.repo_url,
        "report_url": f"https://breakmyapp.tech/scan/{scan.id}",
        "findings_summary": {
            "secrets": findings.get("secrets", {}).get("findings_count", 0),
            "security": findings.get("semgrep", {}).get("findings_count", 0),
            "code_quality": findings.get("bandit", {}).get("findings_count", 0),
            "dependencies": findings.get("dependencies", {}).get("findings_count", 0),
        },
        "top_priorities": ai.get("top_priorities", []) if ai else [],
        "executive_summary": ai.get("executive_summary", "") if ai else "",
    }


@router.get("/{scan_id}/artifacts")
async def get_scan_artifacts(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns presigned artifact download URLs.
    Requires authentication and ownership.
    """
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID '{scan_id}' not found.",
        )

    if scan.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this scan.",
        )

    if scan.status != "completed":
        return {"available": False, "message": "Scan not yet completed."}

    urls = get_artifact_urls(str(scan_id))
    if not urls:
        return {"available": False, "message": "Artifacts not available."}

    return urls


@router.post("/{scan_id}/claim", response_model=ScanResponse)
async def claim_scan(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Attach an anonymous scan to the authenticated user.
    Only claimable within 1 hour of creation to prevent scan theft.
    """
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )

    if scan.user_id is not None and scan.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scan already belongs to another user",
        )

    # Only allow claiming within 1 hour of creation
    now = datetime.now(timezone.utc)
    created = scan.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if now - created > timedelta(hours=1):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scan claim window has expired. Scans can only be claimed within 1 hour of creation.",
        )

    if scan.user_id is None:
        scan.user_id = current_user.id
        await db.commit()
        await db.refresh(scan)

    return scan
