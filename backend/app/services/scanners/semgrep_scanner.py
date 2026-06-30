import os
import json
import logging
import subprocess
from typing import Dict, Any
from app.services.scanners.fp_utils import is_firebase_client_config

logger = logging.getLogger(__name__)

SEVERITY_MAP = {
    "ERROR": "HIGH",
    "WARNING": "MEDIUM",
    "INFO": "LOW"
}


def scan_semgrep(repo_path: str) -> Dict[str, Any]:
    """
    Scans a repository for code quality and security issues using Semgrep.

    Runs Semgrep with the auto config (free community ruleset) against the
    given repository path and returns structured findings with mapped
    severity levels.

    Args:
        repo_path (str): Absolute path to the cloned repository to scan.

    Returns:
        dict: A dictionary containing the scan tool name, status, findings
              count, a list of individual findings, and any error message.
              Always returns this structure even on failure.
    """
    result = {
        "tool": "semgrep",
        "status": "failed",
        "findings_count": 0,
        "findings": [],
        "error": None
    }

    try:
        logger.info(f"Starting Semgrep scan on {repo_path}")
        process = subprocess.run(
            [
                "semgrep", "scan", repo_path,
                "--config", "auto",
                "--json",
                "--no-rewrite-rule-ids",
                "--timeout", "60",
                "--max-memory", "3000",
                "--quiet",
                "--exclude", "node_modules",
                "--exclude", "*.lock",
                "--exclude", "uv.lock",
                "--exclude", "package-lock.json",
                "--exclude", "yarn.lock",
                "--exclude", ".next",
                "--exclude", "dist",
                "--exclude", "build",
                "--exclude", "__pycache__",
                "--exclude", "*.min.js",
                "--exclude", "*.min.css",
                "--exclude", "vendor",
            ],
            capture_output=True,
            text=True,
            timeout=240
        )

        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            logger.error("Failed to parse Semgrep JSON output.")
            result["error"] = "Failed to parse Semgrep output as JSON"
            return result

        errors = output.get("errors", [])
        if errors:
            for err in errors:
                logger.warning(f"Semgrep reported error: {err}")

        results_list = output.get("results", [])

        # Normalise repo_path so stripping works consistently
        repo_prefix = repo_path.rstrip(os.sep) + os.sep

        for item in results_list:
            raw_severity = item.get("extra", {}).get("severity", "")
            mapped_severity = SEVERITY_MAP.get(raw_severity, "LOW")

            raw_path = item.get("path", "")
            if raw_path.startswith(repo_prefix):
                relative_path = raw_path[len(repo_prefix):]
            else:
                relative_path = raw_path

            metadata = item.get("extra", {}).get("metadata", {})

            finding = {
                "severity": mapped_severity,
                "rule_id": item.get("check_id", "unknown"),
                "message": item.get("extra", {}).get("message", ""),
                "file": relative_path,
                "line_start": item.get("start", {}).get("line", 0),
                "line_end": item.get("end", {}).get("line", 0),
                "category": metadata.get("category", "general"),
                "cwe": metadata.get("cwe", [])
            }

            # ------------------------------------------------------------------
            # Firebase client config false-positive suppression
            # Only runs for findings whose rule_id suggests a generic or Google
            # API-key detection. Reads the matched line to confirm the AIzaSy
            # prefix before invoking the heavier file-context check.
            # ------------------------------------------------------------------
            _rule_id_lower = finding["rule_id"].lower()
            if "detected-generic-api-key" in _rule_id_lower or "google" in _rule_id_lower:
                _abs_path = raw_path  # raw_path is already absolute (Semgrep uses full paths)
                _line_start = finding["line_start"]
                _has_aizasy = False
                try:
                    if _abs_path:
                        with open(_abs_path, "r", encoding="utf-8", errors="replace") as _fh:
                            _src_lines = _fh.readlines()
                        _src_line_idx = max(0, _line_start - 1)  # 0-indexed
                        if _src_line_idx < len(_src_lines):
                            _has_aizasy = "AIzaSy" in _src_lines[_src_line_idx]
                except Exception as e:
                    logger.debug(f"Could not read source line for Firebase FP check on {_abs_path}: {e}")

                if _has_aizasy:
                    _is_firebase, _note = is_firebase_client_config(_abs_path, _line_start)
                    if _is_firebase:
                        finding["severity"] = "INFO"
                        finding["message"] = (
                            finding["message"]
                            + " [Verified: Firebase Web SDK client key, safe to expose publicly]"
                        )

            result["findings"].append(finding)

        result["status"] = "completed"
        result["findings_count"] = len(result["findings"])
        logger.info(f"Semgrep scan completed. Found {result['findings_count']} issues.")

    except subprocess.TimeoutExpired:
        logger.error(f"Semgrep scan timed out for {repo_path}")
        result["error"] = "Semgrep scan timed out after 240 seconds"
    except FileNotFoundError:
        logger.error("Semgrep binary not found")
        result["error"] = "semgrep binary not found or not installed"
    except Exception as e:
        logger.error(f"Unexpected error running Semgrep: {e}")
        result["error"] = str(e)

    return result
