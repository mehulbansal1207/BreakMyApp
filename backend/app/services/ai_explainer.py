import json
import logging
import re
from typing import Dict, Any, List

import google.generativeai as genai

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior security engineer reviewing a software project. "
    "Your job is to explain security findings in plain English that "
    "a developer can understand and act on immediately. "
    "Be direct, specific, and actionable. Avoid jargon. "
    "Always respond with valid JSON only, no markdown, no preamble."
)

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _sort_by_severity(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort findings by severity, most critical first."""
    return sorted(
        findings,
        key=lambda f: SEVERITY_ORDER.get(f.get("severity", "LOW"), 3),
    )


def _build_user_prompt(findings: dict, score: int) -> str:
    """Build the user prompt from raw scanner findings and score."""
    parts: List[str] = []

    parts.append(f"Production readiness score: {score}/100")
    parts.append("")

    # --- Repo info ---
    repo_info = findings.get("repo_info", {})
    if repo_info:
        parts.append("## Repository Info")
        parts.append(f"- Languages: {repo_info.get('languages', 'unknown')}")
        parts.append(f"- Has tests: {repo_info.get('has_tests', False)}")
        parts.append(f"- Has CI: {repo_info.get('has_ci', False)}")
        parts.append(f"- Has Dockerfile: {repo_info.get('has_dockerfile', False)}")
        parts.append("")

    # --- Secrets ---
    secrets = findings.get("secrets", {})
    secrets_findings = secrets.get("findings", [])
    parts.append("## Secrets Scan")
    parts.append(f"Found {len(secrets_findings)} exposed secrets/credentials.")
    if secrets_findings:
        for sf in secrets_findings[:5]:
            parts.append(
                f"- Severity: {sf.get('severity', 'UNKNOWN')} | "
                f"Type: {sf.get('detector_name', sf.get('rule_id', 'unknown'))} | "
                f"File: {sf.get('file', 'unknown')}"
            )
    parts.append("")

    # --- Semgrep (top 3) ---
    semgrep = findings.get("semgrep", {})
    semgrep_findings = _sort_by_severity(semgrep.get("findings", []))
    parts.append("## Semgrep Security Scan")
    parts.append(f"Total findings: {len(semgrep_findings)}")
    for sf in semgrep_findings[:3]:
        parts.append(
            f"- [{sf.get('severity', 'LOW')}] Rule: {sf.get('rule_id', 'unknown')} | "
            f"Message: {sf.get('message', '')} | "
            f"File: {sf.get('file', 'unknown')}:{sf.get('line_start', 0)}"
        )
    parts.append("")

    # --- Bandit (top 3) ---
    bandit = findings.get("bandit", {})
    bandit_findings = _sort_by_severity(bandit.get("findings", []))
    parts.append("## Bandit Security Scan")
    parts.append(f"Total findings: {len(bandit_findings)}")
    for bf in bandit_findings[:3]:
        parts.append(
            f"- [{bf.get('severity', 'LOW')}] Test: {bf.get('test_id', 'unknown')} | "
            f"Message: {bf.get('message', '')} | "
            f"File: {bf.get('file', 'unknown')}:{bf.get('line', 0)}"
        )
    parts.append("")

    # --- Dependencies ---
    deps = findings.get("dependencies", {})
    deps_findings = deps.get("findings", [])
    parts.append("## Dependency Vulnerability Scan")
    parts.append(f"Total vulnerable dependencies: {len(deps_findings)}")
    for df in deps_findings:
        parts.append(
            f"- [{df.get('severity', 'LOW')}] Package: {df.get('package', 'unknown')} | "
            f"Vuln: {df.get('vulnerability_id', 'N/A')} | "
            f"Description: {df.get('description', '')}"
        )
    parts.append("")

    # --- Ask for structured JSON ---
    parts.append("Based on the above findings, return a JSON object with this exact schema:")
    parts.append(json.dumps(
        {
            "executive_summary": "2-3 sentence plain English summary",
            "score_explanation": "1-2 sentences explaining why the score is X",
            "top_priorities": [
                {
                    "priority": 1,
                    "title": "short title",
                    "explanation": "plain English explanation",
                    "action": "specific action to take",
                    "severity": "CRITICAL|HIGH|MEDIUM|LOW",
                }
            ],
            "category_summaries": {
                "secrets": "one sentence",
                "security": "one sentence",
                "dependencies": "one sentence",
                "code_quality": "one sentence",
            },
            "positive_findings": ["thing done well", "another thing"],
        },
        indent=2,
    ))
    parts.append("")
    parts.append("Return exactly 3 top_priorities maximum, ordered by severity.")
    parts.append("Return valid JSON only. No markdown fences. No preamble.")

    return "\n".join(parts)


def _empty_result(status: str, error: str) -> Dict[str, Any]:
    """Return the standard result dict with empty/default fields."""
    return {
        "status": status,
        "executive_summary": "",
        "score_explanation": "",
        "top_priorities": [],
        "category_summaries": {
            "secrets": "",
            "security": "",
            "dependencies": "",
            "code_quality": "",
        },
        "positive_findings": [],
        "error": error,
    }


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) if present."""
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", stripped)
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def explain_findings(findings: dict, score: int) -> Dict[str, Any]:
    """Use Claude to generate plain-English explanations of scanner findings.

    Takes the complete findings dictionary produced by the analysis pipeline
    and the computed production-readiness score, sends them to the Anthropic
    Claude API, and returns structured explanations including an executive
    summary, prioritised recommendations, and per-category summaries.

    This layer is optional — the platform works without it.  If the API key
    is missing or the call fails the function returns gracefully with an
    error status rather than raising.

    Args:
        findings: The complete findings dict from analysis.py containing
                  repo_info, secrets, semgrep, bandit, and dependencies.
        score:    The computed production-readiness score (0-100).

    Returns:
        A dictionary with status, executive_summary, score_explanation,
        top_priorities, category_summaries, positive_findings, and error.
    """
    # --- Guard: check API key ---
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.warning("GEMINI_API_KEY not configured — skipping AI explanation.")
        return _empty_result("skipped", "GEMINI_API_KEY not configured")

    # --- Build prompt ---
    user_prompt = _build_user_prompt(findings, score)
    logger.info("Built AI explainer prompt (%d chars).", len(user_prompt))

    # --- Call Gemini API ---
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT
        )
        response = model.generate_content(user_prompt)
        response_text = response.text
        logger.info("Received AI response (%d chars).", len(response_text))
    except Exception as e:
        logger.error("Gemini API call failed: %s", e)
        return _empty_result("failed", str(e))

    # --- Parse JSON response ---
    cleaned_text = _strip_code_fences(response_text)
    try:
        parsed = json.loads(cleaned_text)
    except json.JSONDecodeError:
        logger.error("Failed to parse AI response as JSON. Raw: %s", cleaned_text[:500])
        result = _empty_result("failed", "Failed to parse AI response as JSON")
        result["executive_summary"] = cleaned_text
        return result

    # --- Map parsed response to return structure ---
    result: Dict[str, Any] = {
        "status": "completed",
        "executive_summary": parsed.get("executive_summary", ""),
        "score_explanation": parsed.get("score_explanation", ""),
        "top_priorities": parsed.get("top_priorities", []),
        "category_summaries": parsed.get("category_summaries", {
            "secrets": "",
            "security": "",
            "dependencies": "",
            "code_quality": "",
        }),
        "positive_findings": parsed.get("positive_findings", []),
        "error": None,
    }

    logger.info(
        "AI explanation completed. %d priorities, %d positive findings.",
        len(result["top_priorities"]),
        len(result["positive_findings"]),
    )
    return result
