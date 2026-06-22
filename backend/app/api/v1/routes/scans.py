from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.scan import Scan
from app.schemas.scan import ScanCreate, ScanResponse
from app.tasks.analysis import run_analysis
from app.core.limiter import check_rate_limit

router = APIRouter(prefix="/scans", tags=["scans"])

@router.post("/", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(request: Request, scan_in: ScanCreate, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(ip)

    new_scan = Scan(
        repo_url=scan_in.repo_url,
        status="pending"
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    run_analysis.delay(str(new_scan.id))

    return new_scan

@router.get("/", response_model=list[ScanResponse])
async def list_scans(
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Scan).order_by(Scan.created_at.desc()).limit(limit))
    scans = result.scalars().all()
    return scans

@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID '{scan_id}' not found."
        )
    return scan

@router.get("/{scan_id}/summary")
async def get_scan_summary(scan_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID '{scan_id}' not found."
        )
        
    if scan.status != "completed":
        return {
            "status": scan.status,
            "message": "Scan is not yet complete",
            "score": None
        }
        
    findings = scan.findings or {}
    ai = findings.get("ai_explanation", {})
    
    return {
        "status": "completed",
        "score": scan.score,
        "repo_url": scan.repo_url,
        "report_url": f"https://breakmyapp-production-2f29.up.railway.app/scan/{scan.id}",
        "findings_summary": {
            "secrets": findings.get("secrets", {}).get("findings_count", 0),
            "security": findings.get("semgrep", {}).get("findings_count", 0),
            "code_quality": findings.get("bandit", {}).get("findings_count", 0),
            "dependencies": findings.get("dependencies", {}).get("findings_count", 0),
        },
        "top_priorities": ai.get("top_priorities", []) if ai else [],
        "executive_summary": ai.get("executive_summary", "") if ai else ""
    }
