from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.models.scan import Scan
from app.services.github_reporter import run_github_report

router = APIRouter(prefix="/github", tags=["github"])


class GithubReportRequest(BaseModel):
    token: str
    owner: str
    repo: str
    pr_number: int


@router.post("/report/{scan_id}")
async def post_github_report(
    scan_id: UUID,
    request: GithubReportRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID '{scan_id}' not found."
        )

    if scan.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Scan is not yet complete. Current status: '{scan.status}'."
        )

    findings = scan.findings or {}
    ai = findings.get("ai_explanation", {})

    scan_summary = {
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
        "executive_summary": ai.get("executive_summary", "") if ai else "",
    }

    result_data = await run_github_report(
        token=request.token,
        owner=request.owner,
        repo=request.repo,
        pr_number=request.pr_number,
        scan_id=str(scan.id),
        findings=findings,
        scan_summary=scan_summary,
    )

    return result_data
