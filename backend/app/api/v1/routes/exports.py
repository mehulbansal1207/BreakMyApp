"""
exports.py — Export endpoints for security scan reports.

Provides three endpoints:
  GET  /export/{scan_id}/markdown  → returns Markdown report as plain text
  GET  /export/{scan_id}/pdf       → returns PDF report as binary download
  POST /export/{scan_id}/upload    → generates PDF, uploads to B2/MinIO, returns presigned URL

All endpoints require authentication and scan ownership verification.
"""

from __future__ import annotations

import httpx
import io
import logging
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.scan import Scan
from app.models.user import User
from app.services import export_service
from app.services import minio_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_scan(
    scan_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> Scan:
    """
    Fetch a scan by ID and verify that it belongs to *current_user*.

    Raises:
        404 — scan not found.
        403 — scan.user_id is None (unclaimable / unverifiable) or belongs
               to a different user.
    """
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()

    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan '{scan_id}' not found.",
        )

    # scan.user_id is None → anonymous scan; ownership cannot be verified → deny.
    if scan.user_id is None or scan.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to export this scan.",
        )

    return scan


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{scan_id}/markdown")
async def export_markdown(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> str:
    """
    Return a Markdown-formatted security report for the given scan.

    - **404** if the scan does not exist.
    - **403** if the authenticated user does not own the scan
      (or the scan is anonymous and ownership cannot be verified).
    """
    scan = await _get_owned_scan(scan_id, current_user, db)

    try:
        markdown_content = export_service.generate_markdown(scan)
    except Exception as exc:
        logger.exception("Failed to generate Markdown for scan %s: %s", scan_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate Markdown report.",
        )

    filename = f"breakmyapp-report-{scan_id}.md"
    return Response(
        content=markdown_content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{scan_id}/pdf")
async def export_pdf(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Return a PDF security report for the given scan as a binary download.

    - **404** if the scan does not exist.
    - **403** if the authenticated user does not own the scan.
    """
    scan = await _get_owned_scan(scan_id, current_user, db)

    try:
        pdf_bytes = export_service.generate_pdf(scan)
    except Exception as exc:
        logger.exception("Failed to generate PDF for scan %s: %s", scan_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF report.",
        )

    filename = f"breakmyapp-report-{scan_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get("/{scan_id}/zip")
async def export_zip(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    scan = await _get_owned_scan(scan_id, current_user, db)

    urls = minio_service.get_artifact_urls(str(scan_id))
    if not urls:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No artifacts found for this scan",
        )

    buffer = io.BytesIO()
    downloaded_count = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for key, url in urls.items():
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        zf.writestr(f"{key}.json", resp.content)
                        downloaded_count += 1
                except Exception as exc:
                    logger.warning("Failed to download artifact %s for scan %s: %s", key, scan_id, exc)

    if downloaded_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No artifacts could be retrieved from storage",
        )

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="breakmyapp-artifacts-{str(scan_id)[:8]}.zip"',
        },
    )
