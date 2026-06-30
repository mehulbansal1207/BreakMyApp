import os
import json
import logging
import subprocess
from typing import Dict, Any

logger = logging.getLogger(__name__)

def scan_secrets(repo_path: str) -> Dict[str, Any]:
    """
    Scans a repository for secrets using truffleHog v3.
    
    Args:
        repo_path (str): The path to the repository to scan.
        
    Returns:
        dict: A dictionary containing the scan status and any findings.
    """
    result = {
        "tool": "trufflehog",
        "status": "failed",
        "findings_count": 0,
        "findings": [],
        "error": None
    }
    
    try:
        exclude_patterns = "\n".join([
            ".npm",
            "node_modules",
            ".git",
            "__pycache__",
            r".*\.pyc"
        ])
        process = subprocess.run(
            [
                "trufflehog", "filesystem", repo_path,
                "--json",
                "--no-update",
                "--exclude-paths", "/dev/stdin"
            ],
            input=exclude_patterns,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        for line in process.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
                
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Failed to parse trufflehog output line as JSON. Skipping line.")
                continue
                
            try:
                # Extract fields based on expected Trufflehog v3 JSON structure
                source_metadata = data.get("SourceMetadata", {})
                if source_metadata is None:
                    source_metadata = {}
                    
                meta_data = source_metadata.get("Data", {})
                if meta_data is None:
                    meta_data = {}
                    
                filesystem = meta_data.get("Filesystem", {})
                if filesystem is None:
                    filesystem = {}
                    
                file_path = filesystem.get("file", "")
                line_number = filesystem.get("line", 0)
                
                detector = data.get("DetectorName", "Unknown")
                detector_type = data.get("DetectorType", "Unknown")
                raw_secret = str(data.get("Raw", ""))
                
                # Mask the raw secret: first 4 characters + "****"
                masked_secret = raw_secret[:4] + "****"
                
                finding = {
                    "severity": "CRITICAL",
                    "type": detector_type,
                    "detector": detector,
                    "file": file_path,
                    "line": int(line_number) if line_number else 0,
                    "raw": masked_secret
                }

                # ----------------------------------------------------------
                # Firebase client config false-positive suppression
                # If the detector looks like a Google/Gemini key AND the raw
                # secret has the AIzaSy prefix, check whether it lives inside
                # a Firebase Web SDK config object (safe to expose publicly).
                # ----------------------------------------------------------
                _detector_str = f"{detector_type} {detector}".lower()
                if ("google" in _detector_str or "gemini" in _detector_str) and raw_secret.startswith("AIzaSy"):
                    try:
                        # file_path from TruffleHog is an absolute path when
                        # scanning a filesystem directory directly.
                        with open(file_path, "r", encoding="utf-8", errors="replace") as _fh:
                            _file_lines = _fh.readlines()

                        _match_line = (int(line_number) if line_number else 1) - 1  # 0-indexed
                        _window_start = max(0, _match_line - 10)
                        _window_end = min(len(_file_lines), _match_line + 11)
                        _context = "".join(_file_lines[_window_start:_window_end])

                        _firebase_sibling_keys = [
                            "authDomain",
                            "projectId",
                            "storageBucket",
                            "messagingSenderId",
                            "appId",
                        ]
                        _siblings_found = sum(1 for k in _firebase_sibling_keys if k in _context)

                        if _siblings_found >= 2:
                            # Confirmed Firebase Web SDK client config — not a secret leak
                            finding["severity"] = "INFO"
                            finding["detector"] = "FirebaseClientConfigKey (not a security issue)"
                            finding["note"] = (
                                "This is a Firebase Web SDK client key, which is safe to expose "
                                "publicly. Firebase security relies on Firebase Security Rules and "
                                "authorized domains, not on hiding this key. See: "
                                "https://firebase.google.com/docs/projects/api-keys"
                            )
                    except Exception as _e:
                        # Fail safe: if file can't be read, keep CRITICAL severity unchanged
                        logger.debug(f"Firebase config check failed for {file_path}: {_e}")

                result["findings"].append(finding)

            except Exception as e:
                logger.debug(f"Error extracting data from trufflehog JSON: {e}")
                continue
                
        result["status"] = "completed"
        result["findings_count"] = len(result["findings"])
        
    except subprocess.TimeoutExpired:
        logger.error(f"Trufflehog scan timed out for {repo_path}")
        result["error"] = "Trufflehog scan timed out after 120 seconds"
    except FileNotFoundError:
        logger.error("Trufflehog binary not found")
        result["error"] = "trufflehog binary not found or not installed"
    except Exception as e:
        logger.error(f"Unexpected error running trufflehog: {e}")
        result["error"] = str(e)
        
    return result
