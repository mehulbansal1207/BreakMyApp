import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def _score_emoji(score: int | None) -> str:
    if score is None:
        return "❓"
    if score >= 80:
        return "✅"
    if score >= 60:
        return "⚠️"
    if score >= 40:
        return "🟠"
    return "❌"


def _build_pr_comment(scan_summary: dict) -> str:
    score = scan_summary.get("score")
    findings = scan_summary.get("findings_summary", {})
    secrets_count = findings.get("secrets", 0)
    security_count = findings.get("security", 0)
    code_quality_count = findings.get("code_quality", 0)
    dependencies_count = findings.get("dependencies", 0)
    report_url = scan_summary.get("report_url", "")
    executive_summary = scan_summary.get("executive_summary", "")
    top_priorities = scan_summary.get("top_priorities", [])

    score_display = f"{score}/100 {_score_emoji(score)}" if score is not None else f"N/A {_score_emoji(None)}"

    lines = [
        "## 🔍 BreakMyApp Production Readiness Report",
        "",
        "| Metric | Result |",
        "|--------|--------|",
        f"| Score | {score_display} |",
        f"| Secrets | {secrets_count} |",
        f"| Security Issues | {security_count} |",
        f"| Code Quality | {code_quality_count} |",
        f"| Vulnerable Dependencies | {dependencies_count} |",
        "",
    ]

    if executive_summary:
        lines.append(executive_summary)
        lines.append("")

    if top_priorities:
        lines.append("**Top Priorities:**")
        for i, priority in enumerate(top_priorities, 1):
            severity = priority.get("severity", "")
            title = priority.get("title", "")
            lines.append(f"{i}. **[{severity}]** {title}")
        lines.append("")

    lines.append("---")
    lines.append(
        f"📊 [View Full Report]({report_url}) | "
        "🔧 Powered by [BreakMyApp](https://breakmyapp-production-2f29.up.railway.app)"
    )

    return "\n".join(lines)


async def post_pr_comment(
    token: str,
    owner: str,
    repo: str,
    pr_number: int,
    scan_summary: dict
) -> bool:
    """
    Posts a formatted BreakMyApp scan summary comment on a GitHub PR.

    Returns True if the comment was posted successfully, False otherwise.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    body = {"body": _build_pr_comment(scan_summary)}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=body, timeout=15)
            if response.is_success:
                logger.info(f"Posted PR comment on {owner}/{repo}#{pr_number}")
                return True
            else:
                logger.error(
                    f"Failed to post PR comment: {response.status_code} {response.text}"
                )
                return False
    except Exception as e:
        logger.error(f"Exception posting PR comment: {e}")
        return False


def _build_issue_title(category: str, finding: dict) -> str:
    severity = finding.get("severity", "UNKNOWN")
    if category == "secrets":
        detector = finding.get("detector", "Unknown")
        file_ = finding.get("file", "unknown file")
        short = f"{detector} credential detected in {file_}"
    elif category == "semgrep":
        rule_id = finding.get("rule_id", "unknown")
        file_ = finding.get("file", "unknown file")
        line = finding.get("line_start", "?")
        short = f"{rule_id} in {file_}:{line}"
    elif category == "bandit":
        test_name = finding.get("test_name", finding.get("test_id", "unknown"))
        file_ = finding.get("file", "unknown file")
        line = finding.get("line", "?")
        short = f"{test_name} in {file_}:{line}"
    elif category == "dependencies":
        package = finding.get("package", "unknown")
        vuln_id = finding.get("vulnerability_id", "unknown")
        short = f"Vulnerable dependency: {package} ({vuln_id})"
    else:
        short = finding.get("message", "Security finding")

    return f"[BreakMyApp] {severity}: {short}"


def _build_issue_body(category: str, finding: dict, scan_summary: dict) -> str:
    severity = finding.get("severity", "UNKNOWN")
    file_ = finding.get("file", finding.get("package", "N/A"))
    line = (
        finding.get("line")
        or finding.get("line_start")
        or "N/A"
    )
    report_url = scan_summary.get("report_url", "")

    if category == "secrets":
        message = f"{finding.get('detector', 'Unknown')} credential detected. Raw preview: `{finding.get('raw', '')}`"
        cat_label = "Secrets & Credentials"
    elif category == "semgrep":
        message = finding.get("message", "")
        cat_label = "Static Security (SAST)"
    elif category == "bandit":
        message = finding.get("message", "")
        cat_label = "Code Quality & Security"
    elif category == "dependencies":
        message = finding.get("description", "")
        cat_label = "Vulnerable Dependencies"
    else:
        message = finding.get("message", "")
        cat_label = category.capitalize()

    # Try to find a matching remediation from top_priorities
    top_priorities = scan_summary.get("top_priorities", [])
    remediation = None
    for priority in top_priorities:
        if priority.get("severity") == severity:
            remediation = priority.get("action")
            break
    if not remediation:
        remediation = f"Review and fix this {severity} severity issue."

    lines = [
        "## 🔍 BreakMyApp Security Finding",
        "",
        f"**Severity:** {severity}",
        f"**Category:** {cat_label}",
        f"**File:** `{file_}`",
        f"**Line:** {line}",
        "",
        "### Description",
        message,
        "",
        "### Remediation",
        remediation,
        "",
        "---",
        f"🔗 [View Full Scan Report]({report_url})",
        "*Detected by [BreakMyApp](https://breakmyapp-production-2f29.up.railway.app)*",
    ]

    return "\n".join(lines)


async def create_github_issues(
    token: str,
    owner: str,
    repo: str,
    scan_summary: dict,
    findings: dict
) -> int:
    """
    Creates GitHub Issues for all HIGH and CRITICAL findings.

    Returns the count of issues successfully created.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    category_map = {
        "secrets": findings.get("secrets", {}).get("findings", []),
        "semgrep": findings.get("semgrep", {}).get("findings", []),
        "bandit": findings.get("bandit", {}).get("findings", []),
        "dependencies": findings.get("dependencies", {}).get("findings", []),
    }

    issues_created = 0

    async with httpx.AsyncClient() as client:
        for category, category_findings in category_map.items():
            for finding in category_findings:
                severity = finding.get("severity", "").upper()
                if severity not in ("HIGH", "CRITICAL"):
                    continue

                title = _build_issue_title(category, finding)
                body = _build_issue_body(category, finding, scan_summary)
                labels = ["breakmyapp", "security", severity.lower()]
                payload = {"title": title, "body": body, "labels": labels}

                try:
                    response = await client.post(url, headers=headers, json=payload, timeout=15)
                    if response.is_success:
                        issues_created += 1
                        logger.info(f"Created GitHub issue: {title}")
                    else:
                        logger.error(
                            f"Failed to create issue '{title}': "
                            f"{response.status_code} {response.text}"
                        )
                except Exception as e:
                    logger.error(f"Exception creating issue '{title}': {e}")

                # Delay to avoid GitHub rate limiting
                await asyncio.sleep(0.5)

    return issues_created


async def run_github_report(
    token: str,
    owner: str,
    repo: str,
    pr_number: int,
    scan_id: str,
    findings: dict,
    scan_summary: dict
) -> dict:
    """
    Orchestrates posting a PR comment and creating GitHub issues.

    Returns a summary dict with comment_posted, issues_created, and errors.
    """
    errors = []

    comment_posted = await post_pr_comment(
        token=token,
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        scan_summary=scan_summary,
    )
    if not comment_posted:
        errors.append("Failed to post PR comment.")

    issues_created = await create_github_issues(
        token=token,
        owner=owner,
        repo=repo,
        scan_summary=scan_summary,
        findings=findings,
    )

    return {
        "comment_posted": comment_posted,
        "issues_created": issues_created,
        "errors": errors,
    }
