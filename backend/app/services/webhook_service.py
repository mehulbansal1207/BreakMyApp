import json
import logging
import time
import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)


def build_webhook_payload(scan_id: str, scan: Any) -> dict:
    """
    Build the webhook POST body from a completed scan object.
    scan is a SQLAlchemy Scan model instance.
    """
    findings: dict = scan.findings or {}
    ai: dict = findings.get("ai_explanation", {})

    return {
        "event": "scan.completed",
        "scan_id": str(scan.id),
        "repo_url": scan.repo_url,
        "status": scan.status,
        "score": scan.score,
        "report_url": f"https://breakmyapp.tech/scan/{scan.id}",
        "findings_summary": {
            "secrets": findings.get("secrets", {}).get("findings_count", 0),
            "security": findings.get("semgrep", {}).get("findings_count", 0),
            "code_quality": findings.get("bandit", {}).get("findings_count", 0),
            "dependencies": findings.get("dependencies", {}).get("findings_count", 0),
        },
        "top_priorities": ai.get("top_priorities", [])[:3] if ai else [],
        "executive_summary": ai.get("executive_summary", "") if ai else "",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


def fire_webhook(scan_id: str, callback_url: str, payload: dict) -> bool:
    """
    POST payload as JSON to callback_url.
    Retries up to 3 times with 2s delay between attempts.
    Timeout: 10s per attempt.
    Returns True if any attempt succeeds (2xx response).
    Returns False if all attempts fail.
    Never raises — all exceptions caught internally.
    """
    max_attempts: int = 3

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                callback_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "BreakMyApp-Webhook/1.0",
                },
                timeout=10,
            )
            if 200 <= response.status_code <= 299:
                logger.info(
                    "Webhook delivered successfully for scan %s to %s (attempt %d, status %d).",
                    scan_id,
                    callback_url,
                    attempt,
                    response.status_code,
                )
                return True
            else:
                logger.warning(
                    "Webhook attempt %d for scan %s returned non-2xx status %d.",
                    attempt,
                    scan_id,
                    response.status_code,
                )
        except requests.RequestException as exc:
            logger.warning(
                "Webhook attempt %d for scan %s failed: %s.",
                attempt,
                scan_id,
                exc,
            )

        if attempt < max_attempts:
            time.sleep(2)

    logger.error(
        "All %d webhook attempts exhausted for scan %s. Callback URL: %s.",
        max_attempts,
        scan_id,
        callback_url,
    )
    return False
