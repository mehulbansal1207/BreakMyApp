import os
import json
import shutil
import logging
import subprocess
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

NPM_SEVERITY_MAP = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "moderate": "MEDIUM",
    "low": "LOW",
}


def _infer_severity_from_description(description: str) -> str:
    """Infer a severity level from the vulnerability description text.

    pip-audit does not provide an explicit severity field, so we fall back
    to keyword matching against the description string.
    """
    desc_lower = description.lower()
    if "critical" in desc_lower:
        return "CRITICAL"
    if "high" in desc_lower:
        return "HIGH"
    if "medium" in desc_lower:
        return "MEDIUM"
    return "LOW"


def _scan_python(repo_path: str) -> Dict[str, Any]:
    """Run pip-audit against a requirements.txt file in *repo_path*.

    Returns a sub-result dict with status, findings_count, findings list,
    and error (if any).
    """
    sub_result: Dict[str, Any] = {
        "status": "skipped",
        "findings_count": 0,
        "error": None,
    }
    findings: List[Dict[str, Any]] = []

    requirements_file = os.path.join(repo_path, "requirements.txt")
    if not os.path.isfile(requirements_file):
        logger.info("No requirements.txt found in %s — skipping Python scan.", repo_path)
        sub_result["error"] = "No requirements.txt found"
        return sub_result, findings

    if shutil.which("pip-audit") is None:
        logger.error("pip-audit binary not found on PATH.")
        sub_result["status"] = "failed"
        sub_result["error"] = "pip-audit not installed"
        return sub_result, findings

    try:
        logger.info("Starting pip-audit scan on %s", requirements_file)
        process = subprocess.run(
            ["pip-audit", "-r", requirements_file, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            logger.error("Failed to parse pip-audit JSON output. stderr: %s", process.stderr)
            sub_result["status"] = "failed"
            sub_result["error"] = "Failed to parse pip-audit output as JSON"
            return sub_result, findings

        dependencies = output.get("dependencies", [])
        for dep in dependencies:
            package_name = dep.get("name", "unknown")
            installed_version = dep.get("version", "unknown")
            vulns = dep.get("vulns", [])

            for vuln in vulns:
                description = vuln.get("description", "")
                fix_versions = vuln.get("fix_versions", [])

                finding = {
                    "severity": _infer_severity_from_description(description),
                    "package": package_name,
                    "installed_version": installed_version,
                    "fix_version": fix_versions[0] if fix_versions else "N/A",
                    "vulnerability_id": vuln.get("id", "N/A"),
                    "description": description,
                    "ecosystem": "python",
                }
                findings.append(finding)

        sub_result["status"] = "completed"
        sub_result["findings_count"] = len(findings)
        logger.info("pip-audit scan completed. Found %d vulnerabilities.", len(findings))

    except subprocess.TimeoutExpired:
        logger.error("pip-audit scan timed out for %s", repo_path)
        sub_result["status"] = "failed"
        sub_result["error"] = "pip-audit scan timed out after 120 seconds"
    except FileNotFoundError:
        logger.error("pip-audit binary not found.")
        sub_result["status"] = "failed"
        sub_result["error"] = "pip-audit not installed"
    except Exception as e:
        logger.error("Unexpected error running pip-audit: %s", e)
        sub_result["status"] = "failed"
        sub_result["error"] = str(e)

    return sub_result, findings


def _scan_javascript(repo_path: str) -> Dict[str, Any]:
    """Run npm audit against a package.json in *repo_path*.

    Returns a sub-result dict with status, findings_count, findings list,
    and error (if any).
    """
    sub_result: Dict[str, Any] = {
        "status": "skipped",
        "findings_count": 0,
        "error": None,
    }
    findings: List[Dict[str, Any]] = []

    package_json = os.path.join(repo_path, "package.json")
    if not os.path.isfile(package_json):
        logger.info("No package.json found in %s — skipping JavaScript scan.", repo_path)
        sub_result["error"] = "No package.json found"
        return sub_result, findings

    if shutil.which("npm") is None:
        logger.warning("npm binary not available in container — skipping JavaScript scan.")
        sub_result["error"] = "npm not available in container"
        return sub_result, findings

    try:
        logger.info("Starting npm audit scan on %s", repo_path)
        process = subprocess.run(
            ["npm", "audit", "--json"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=60,
        )

        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            logger.error("Failed to parse npm audit JSON output. stderr: %s", process.stderr)
            sub_result["status"] = "failed"
            sub_result["error"] = "Failed to parse npm audit output as JSON"
            return sub_result, findings

        vulnerabilities = output.get("vulnerabilities", {})
        for vuln_name, vuln_data in vulnerabilities.items():
            raw_severity = vuln_data.get("severity", "low")
            severity = NPM_SEVERITY_MAP.get(raw_severity, "LOW")

            # Determine fix_version from fixAvailable field
            fix_available = vuln_data.get("fixAvailable", False)
            if isinstance(fix_available, dict):
                fix_version = fix_available.get("version", "N/A")
            elif fix_available is True:
                fix_version = "Available (run npm audit fix)"
            else:
                fix_version = "N/A"

            # Extract vulnerability_id and description from the via array
            via = vuln_data.get("via", [])
            vulnerability_id = "N/A"
            description = vuln_data.get("name", vuln_name)

            for via_entry in via:
                if isinstance(via_entry, dict):
                    if via_entry.get("id"):
                        vulnerability_id = str(via_entry["id"])
                    if via_entry.get("title"):
                        description = via_entry["title"]
                    break

            finding = {
                "severity": severity,
                "package": vuln_data.get("name", vuln_name),
                "installed_version": vuln_data.get("range", "unknown"),
                "fix_version": fix_version,
                "vulnerability_id": vulnerability_id,
                "description": description,
                "ecosystem": "javascript",
            }
            findings.append(finding)

        sub_result["status"] = "completed"
        sub_result["findings_count"] = len(findings)
        logger.info("npm audit scan completed. Found %d vulnerabilities.", len(findings))

    except subprocess.TimeoutExpired:
        logger.error("npm audit scan timed out for %s", repo_path)
        sub_result["status"] = "failed"
        sub_result["error"] = "npm audit scan timed out after 60 seconds"
    except FileNotFoundError:
        logger.error("npm binary not found.")
        sub_result["status"] = "skipped"
        sub_result["error"] = "npm not available in container"
    except Exception as e:
        logger.error("Unexpected error running npm audit: %s", e)
        sub_result["status"] = "failed"
        sub_result["error"] = str(e)

    return sub_result, findings


def scan_dependencies(repo_path: str) -> Dict[str, Any]:
    """Run dependency vulnerability scanning against a cloned repository.

    Scans for known vulnerabilities in both Python (via pip-audit) and
    JavaScript (via npm audit) dependency manifests found at the root of
    *repo_path*.  Each ecosystem is scanned independently — a failure or
    skip in one does not prevent the other from running.

    Args:
        repo_path: Absolute path to the cloned repository to scan.

    Returns:
        A dictionary with the following top-level keys:
            tool            – always ``"dependency_scanner"``
            status          – ``"completed"`` (even when individual scans
                              are skipped or fail)
            findings_count  – total number of vulnerability findings
            findings        – list of finding dicts (see module docstring)
            python_scan     – sub-result for the Python ecosystem scan
            javascript_scan – sub-result for the JavaScript ecosystem scan
            error           – ``None`` unless a truly unexpected error occurs
    """
    result: Dict[str, Any] = {
        "tool": "dependency_scanner",
        "status": "completed",
        "findings_count": 0,
        "findings": [],
        "python_scan": {
            "status": "skipped",
            "findings_count": 0,
            "error": None,
        },
        "javascript_scan": {
            "status": "skipped",
            "findings_count": 0,
            "error": None,
        },
        "error": None,
    }

    all_findings: List[Dict[str, Any]] = []

    # --- Python scan ---
    try:
        python_sub, python_findings = _scan_python(repo_path)
        result["python_scan"] = python_sub
        all_findings.extend(python_findings)
    except Exception as e:
        logger.error("Critical failure in Python dependency scan: %s", e)
        result["python_scan"]["status"] = "failed"
        result["python_scan"]["error"] = str(e)

    # --- JavaScript scan ---
    try:
        javascript_sub, javascript_findings = _scan_javascript(repo_path)
        result["javascript_scan"] = javascript_sub
        all_findings.extend(javascript_findings)
    except Exception as e:
        logger.error("Critical failure in JavaScript dependency scan: %s", e)
        result["javascript_scan"]["status"] = "failed"
        result["javascript_scan"]["error"] = str(e)

    result["findings"] = all_findings
    result["findings_count"] = len(all_findings)

    logger.info(
        "Dependency scan finished. Python: %s (%d findings), JavaScript: %s (%d findings)",
        result["python_scan"]["status"],
        result["python_scan"]["findings_count"],
        result["javascript_scan"]["status"],
        result["javascript_scan"]["findings_count"],
    )

    return result
