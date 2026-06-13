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
        # Run trufflehog without check=True because it may return non-zero exit code if secrets are found
        process = subprocess.run(
            ["trufflehog", "filesystem", repo_path, "--json", "--no-update"],
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
