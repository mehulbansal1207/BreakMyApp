from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.models.scan import Scan
from app.services.github_reporter import run_github_report, create_github_issues
from app.core.config import settings
from app.core.auth import get_current_user
from app.core.limiter import check_rate_limit

router = APIRouter(prefix="/github", tags=["github"])


class GithubReportRequest(BaseModel):
    token: str
    owner: str
    repo: str
    pr_number: int


class GithubCreateIssuesRequest(BaseModel):
    token: str


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


@router.post("/scans/{scan_id}/create-issues")
async def create_issues_for_scan(
    scan_id: UUID,
    request: GithubCreateIssuesRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Rate limit: 5 issue-creation requests per user per hour
    await check_rate_limit(
        identifier=str(current_user.id),
        key_prefix="ratelimit:issues",
        limit=5,
        window_seconds=3600,
    )

    # Fetch scan
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()

    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID '{scan_id}' not found."
        )

    # Must be completed
    if scan.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scan must be completed before creating issues"
        )

    # Must have findings
    if scan.findings is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No findings available for this scan"
        )

    # Parse owner and repo from repo_url
    # Expected format: https://github.com/{owner}/{repo}[.git]
    try:
        url = scan.repo_url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        parts = url.split("github.com/", 1)
        if len(parts) != 2:
            raise ValueError("Not a GitHub URL")
        path_parts = parts[1].split("/")
        if len(path_parts) < 2:
            raise ValueError("Missing owner or repo")
        owner = path_parts[0]
        repo = path_parts[1]
        if not owner or not repo:
            raise ValueError("Empty owner or repo")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse GitHub repository from scan URL"
        )

    # Build scan_summary
    scan_summary = {
        "score": scan.score,
        "report_url": f"https://breakmyapp.tech/scan/{scan.id}",
        "executive_summary": scan.findings.get("ai_explanation", {}).get("executive_summary", ""),
        "top_priorities": scan.findings.get("ai_explanation", {}).get("top_priorities", []),
        "findings_summary": {
            "secrets": scan.findings.get("secrets", {}).get("findings_count", 0),
            "security": scan.findings.get("semgrep", {}).get("findings_count", 0),
            "code_quality": scan.findings.get("bandit", {}).get("findings_count", 0),
            "dependencies": scan.findings.get("dependencies", {}).get("findings_count", 0),
        },
    }

    # Create GitHub issues using the caller's own GitHub token
    issues_created = await create_github_issues(
        token=request.token,
        owner=owner,
        repo=repo,
        scan_summary=scan_summary,
        findings=scan.findings,
    )

    return {
        "issues_created": issues_created,
        "repo": f"{owner}/{repo}",
        "scan_id": str(scan.id),
    }

