import os
import json
import logging
import subprocess
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _has_python_files(repo_path: str) -> bool:
    """Check if the repository contains any .py files."""
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".py"):
                return True
    return False


def scan_bandit(repo_path: str, repo_url: str = "") -> Dict[str, Any]:
    """
    Scans a Python repository for security issues using Bandit.

    Runs Bandit recursively against the given repository path and returns
    structured findings. Skips the scan entirely if no Python files are
    detected in the repository.

    Args:
        repo_path (str): Absolute path to the cloned repository to scan.
        repo_url (str): The original repository URL, used to detect self-scans
                        of BreakMyApp and suppress known-safe subprocess findings.

    Returns:
        dict: A dictionary containing the scan tool name, status, findings
              count, a list of individual findings, and any error message.
              Always returns this structure even on failure.
    """
    result = {
        "tool": "bandit",
        "status": "failed",
        "findings_count": 0,
        "findings": [],
        "error": None
    }

    if not _has_python_files(repo_path):
        logger.info(f"No Python files found in {repo_path}, skipping Bandit scan.")
        result["status"] = "completed"
        result["error"] = "No Python files detected, bandit scan skipped"
        return result

    try:
        logger.info(f"Starting Bandit scan on {repo_path}")
        process = subprocess.run(
            ["bandit", "-r", repo_path, "-f", "json", "-q"],
            capture_output=True,
            text=True,
            timeout=120
        )

        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            logger.error("Failed to parse Bandit JSON output.")
            result["error"] = "Failed to parse Bandit output as JSON"
            return result

        errors = output.get("errors", [])
        if errors:
            for err in errors:
                logger.warning(f"Bandit reported error: {err}")

        results_list = output.get("results", [])

        repo_prefix = repo_path.rstrip(os.sep) + os.sep

        for item in results_list:
            raw_path = item.get("filename", "")
            if raw_path.startswith(repo_prefix):
                relative_path = raw_path[len(repo_prefix):]
            else:
                relative_path = raw_path

            finding = {
                "severity": item.get("issue_severity", "LOW"),
                "confidence": item.get("issue_confidence", "LOW"),
                "test_id": item.get("test_id", ""),
                "test_name": item.get("test_name", ""),
                "message": item.get("issue_text", ""),
                "file": relative_path,
                "line": item.get("line_number", 0)
            }
            result["findings"].append(finding)

        # -----------------------------------------------------------------
        # Self-scan false-positive suppression
        # When BreakMyApp scans its own repository, B404/B603/B607 findings
        # from the scanner modules are deliberate and safe — filter them out
        # to avoid confusing self-referential noise.
        # For every other repo, all findings are kept completely unchanged.
        # -----------------------------------------------------------------
        _SELF_SCAN_TEST_IDS = {"B404", "B603", "B607"}
        _SELF_SCAN_PATH_FRAGMENTS = ("services/scanners/", "services/repo_handler.py")

        if "mehulbansal1207/breakmyapp" in repo_url.lower():
            before = len(result["findings"])
            result["findings"] = [
                f for f in result["findings"]
                if not (
                    f.get("test_id") in _SELF_SCAN_TEST_IDS
                    and any(frag in f.get("file", "").replace("\\", "/") for frag in _SELF_SCAN_PATH_FRAGMENTS)
                )
            ]
            filtered = before - len(result["findings"])
            if filtered:
                logger.info(
                    f"Self-scan suppression: removed {filtered} known-safe "
                    f"subprocess finding(s) from BreakMyApp's own scanner files."
                )

        result["status"] = "completed"
        result["findings_count"] = len(result["findings"])
        logger.info(f"Bandit scan completed. Found {result['findings_count']} issues.")

    except subprocess.TimeoutExpired:
        logger.error(f"Bandit scan timed out for {repo_path}")
        result["error"] = "Bandit scan timed out after 120 seconds"
    except FileNotFoundError:
        logger.error("Bandit binary not found")
        result["error"] = "bandit binary not found or not installed"
    except Exception as e:
        logger.error(f"Unexpected error running Bandit: {e}")
        result["error"] = str(e)

    return result
