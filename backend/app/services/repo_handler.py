import os
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

def clone_repo(repo_url: str) -> str:
    """
    Clones a GitHub repository into a unique temporary directory.
    
    Args:
        repo_url (str): The URL of the repository to clone.
        
    Returns:
        str: The path to the temporary directory containing the cloned repository.
        
    Raises:
        RuntimeError: If the git clone command fails or times out.
    """
    target_dir = tempfile.mkdtemp(prefix="breakmyapp_")
    logger.info(f"Starting to clone {repo_url} into {target_dir}")
    
    try:
        # Run git clone with a 60-second timeout
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, target_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        logger.info(f"Successfully cloned {repo_url} into {target_dir}")
        return target_dir
    except subprocess.TimeoutExpired as e:
        logger.error(f"Timeout while cloning {repo_url}: {e}")
        cleanup_repo(target_dir)
        raise RuntimeError(f"Timeout expired while cloning {repo_url}") from e
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone {repo_url}. Error: {e.stderr}")
        cleanup_repo(target_dir)
        stderr_msg = e.stderr or ""
        if "Repository not found" in stderr_msg or "does not exist" in stderr_msg or "not found" in stderr_msg:
            raise RuntimeError(
                "Repository not found. Please check the URL is correct and "
                "the repository is public."
            )
        elif "Authentication failed" in stderr_msg or "could not read Username" in stderr_msg or "terminal prompts disabled" in stderr_msg:
            raise RuntimeError(
                "This repository is private. BreakMyApp can only scan "
                "public repositories."
            )
        elif "Connection refused" in stderr_msg or "Could not resolve host" in stderr_msg or "Failed to connect" in stderr_msg:
            raise RuntimeError(
                "Could not connect to GitHub. Please check the URL and "
                "try again."
            )
        else:
            raise RuntimeError(
                f"Failed to clone repository. Please ensure the URL is "
                f"correct and the repository is public. "
                f"Details: {stderr_msg[:200]}"
            )
    except Exception as e:
        logger.error(f"Unexpected error while cloning {repo_url}: {e}")
        cleanup_repo(target_dir)
        raise RuntimeError(f"Unexpected error while cloning {repo_url}: {e}") from e

def cleanup_repo(repo_path: str) -> None:
    """
    Deletes the directory at repo_path and all its contents.
    
    Args:
        repo_path (str): The path to the directory to be deleted.
    """
    if not os.path.exists(repo_path):
        return
        
    try:
        shutil.rmtree(repo_path)
        logger.info(f"Successfully cleaned up repository at {repo_path}")
    except Exception as e:
        logger.warning(f"Failed to clean up repository at {repo_path}. Error: {e}")

def get_repo_info(repo_path: str) -> Dict[str, Any]:
    """
    Analyzes a cloned repository and returns information about its contents.
    
    Args:
        repo_path (str): The path to the cloned repository.
        
    Returns:
        dict: A dictionary containing information about the repository.
    """
    info = {
        "languages": [],
        "has_python": False,
        "has_javascript": False,
        "has_dockerfile": False,
        "has_ci": False,
        "has_tests": False,
        "has_requirements": False,
        "has_package_json": False,
        "total_files": 0,
        "repo_size_mb": 0.0
    }
    
    languages_found = set()
    total_size_bytes = 0
    repo_path_obj = Path(repo_path)
    
    # Pre-calculate paths for CI checks
    github_ci_path = repo_path_obj / ".github" / "workflows"
    gitlab_ci_path = repo_path_obj / ".gitlab-ci.yml"
    
    if (github_ci_path.exists() and github_ci_path.is_dir()) or gitlab_ci_path.exists():
        info["has_ci"] = True

    # Directories that indicate tests
    test_dir_names = {"test", "tests", "__tests__"}
    
    # Files that indicate requirements
    requirement_file_names = {"requirements.txt", "pipfile", "pyproject.toml"}

    for root, dirs, files in os.walk(repo_path):
        # Check for test directories
        for d in dirs:
            if d.lower() in test_dir_names:
                info["has_tests"] = True
                
        for file in files:
            info["total_files"] += 1
            file_path = os.path.join(root, file)
            
            # Add to total size
            try:
                if not os.path.islink(file_path):
                    total_size_bytes += os.path.getsize(file_path)
            except OSError:
                pass
                
            # Check for specific files
            file_lower = file.lower()
            if file_lower == "dockerfile":
                info["has_dockerfile"] = True
            elif file_lower in requirement_file_names:
                info["has_requirements"] = True
            elif file_lower == "package.json":
                info["has_package_json"] = True
                
            # Check file extensions for languages
            _, ext = os.path.splitext(file_lower)
            if ext == ".py":
                info["has_python"] = True
                languages_found.add("Python")
            elif ext == ".js":
                info["has_javascript"] = True
                languages_found.add("JavaScript")
            elif ext == ".ts":
                info["has_javascript"] = True
                languages_found.add("TypeScript")
            elif ext == ".java":
                languages_found.add("Java")
            elif ext == ".go":
                languages_found.add("Go")
            elif ext == ".rs":
                languages_found.add("Rust")
            elif ext == ".rb":
                languages_found.add("Ruby")
            elif ext == ".php":
                languages_found.add("PHP")

    info["languages"] = sorted(list(languages_found))
    info["repo_size_mb"] = total_size_bytes / (1024 * 1024)
    
    return info
