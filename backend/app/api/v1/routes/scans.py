from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.scan import Scan
from app.schemas.scan import ScanCreate, ScanResponse
from app.tasks.analysis import run_analysis

router = APIRouter(prefix="/scans", tags=["scans"])

@router.post("/", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(scan_in: ScanCreate, db: AsyncSession = Depends(get_db)):
    new_scan = Scan(
        repo_url=scan_in.repo_url,
        status="pending"
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    run_analysis.delay(str(new_scan.id))

    return new_scan

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
