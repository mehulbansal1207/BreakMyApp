"""Dynamic scan task — Phase 3b Python app-runner.

Executes untrusted Python repos inside the Phase 3a gVisor sandbox using a
prefetch-then-install pattern.  The sandbox network (sandbox-net, internal:
true) blocks ALL outbound network access.  Dependencies are prefetched on
the trusted worker (outside the sandbox) and copied in via ``docker cp``.

Pipeline:
  1. Clone repo (reuse repo_handler.clone_repo)
  2. Detect Python manifest (requirements.txt / pyproject.toml)
  3. Prefetch wheels on worker (pip download)
  4. Start sandbox container (docker run -d)
  5. Copy repo + wheels into container (docker cp)
  6. Install deps inside sandbox (pip install --no-index)
  7. Detect entrypoint (Procfile web: → main.py → app.py)
  8. Start app inside sandbox (docker exec -d)
  9. Poll for TCP port (ss -tlnp)
 10. Cleanup (always, in finally)

All ``docker`` CLI calls go through the DOCKER_HOST environment variable,
which points at the Tecnativa/docker-socket-proxy service
(``tcp://docker-socket-proxy:2375``).  No code in this module assumes a
local unix socket path — all calls simply invoke the ``docker`` binary and
let it resolve the connection from DOCKER_HOST.
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib  # Python 3.11+ (standard library)
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

from app.celery_app import celery_app
from app.core.config import settings
from app.models.scan import Scan
from app.services.repo_handler import clone_repo, cleanup_repo


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Sandbox configuration — loaded from sandbox/sandbox_config.env
#
# These values MUST match the Phase 3a verified limits.  Do not override
# them here — change only in sandbox_config.env (Phase 3a owns that file).
# Defaults are provided as a safety net in case the file is not found
# (e.g. during local dev), but they mirror the production values exactly.
# ---------------------------------------------------------------------------

def _load_sandbox_config() -> dict:
    """Parse sandbox/sandbox_config.env and return a dict of key=value pairs.

    Searches multiple candidate paths to handle both local dev (repo root)
    and production (Docker container /app).
    """
    config: dict[str, str] = {}
    config_paths = [
        # From backend/app/tasks/dynamic_scan.py → repo root
        Path(__file__).resolve().parents[3] / "sandbox" / "sandbox_config.env",
        # Inside production container: /app is WORKDIR, sandbox/ is sibling
        Path("/sandbox") / "sandbox_config.env",
        # Relative fallback
        Path("sandbox") / "sandbox_config.env",
    ]
    for p in config_paths:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        config[key.strip()] = value.strip()
            logger.info(f"Loaded sandbox config from {p}")
            break
    else:
        logger.warning(
            "sandbox_config.env not found at any expected path — "
            "using hardcoded defaults matching Phase 3a production values."
        )
    return config


_SANDBOX_CFG = _load_sandbox_config()

# Resource limits — read from config, with safe defaults matching Phase 3a
SANDBOX_MEMORY_LIMIT = _SANDBOX_CFG.get("SANDBOX_MEMORY_LIMIT", "512m")
SANDBOX_MEMORY_SWAP = _SANDBOX_CFG.get("SANDBOX_MEMORY_SWAP", "512m")
SANDBOX_CPU_LIMIT = _SANDBOX_CFG.get("SANDBOX_CPU_LIMIT", "1.0")
SANDBOX_PID_LIMIT = _SANDBOX_CFG.get("SANDBOX_PID_LIMIT", "256")
SANDBOX_TMP_SIZE = _SANDBOX_CFG.get("SANDBOX_TMP_SIZE", "256M")
SANDBOX_VAR_TMP_SIZE = _SANDBOX_CFG.get("SANDBOX_VAR_TMP_SIZE", "64M")
SANDBOX_WORKSPACE_SIZE = _SANDBOX_CFG.get("SANDBOX_WORKSPACE_SIZE", "512M")
SANDBOX_TIMEOUT_SECONDS = int(
    _SANDBOX_CFG.get("SANDBOX_TIMEOUT_SECONDS", "300")
)
SANDBOX_RUNTIME = _SANDBOX_CFG.get("SANDBOX_RUNTIME", "runsc")
SANDBOX_IMAGE = "breakmyapp-scan-runner:latest"

# CORRECTION 2 — Network name.
# Docker Compose auto-prefixes network names with the project directory name.
# sandbox/docker-compose.sandbox.yml defines "sandbox-net" within project
# "sandbox", so the actual Docker network name is "sandbox_sandbox-net".
# Verified working via verify_sandbox.sh on the production droplet.
# We do NOT modify docker-compose.sandbox.yml's network definition.
SANDBOX_NETWORK = "sandbox_sandbox-net"

# Startup poll timeout — SEPARATE from SANDBOX_TIMEOUT_SECONDS (300s).
# Most Python web servers (Flask, Django, FastAPI) bind their port within
# 5-10s.  Burning the full 300s sandbox timeout on every failed startup
# wastes worker capacity.  30s is generous enough for slow frameworks while
# keeping the failure-feedback loop tight for users.
STARTUP_POLL_TIMEOUT = 30
STARTUP_POLL_INTERVAL = 2  # seconds between port checks

# Pip output truncation — errors always live at the end of the stream
MAX_OUTPUT_CHARS = 4000


# ---------------------------------------------------------------------------
# Database helpers — same pattern as analysis.py
# ---------------------------------------------------------------------------

def _get_task_session():
    """Create a dedicated engine + session_factory for this task invocation."""
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return engine, session_factory


async def _update_dynamic_status(
    session_factory,
    scan_uuid: UUID,
    status: str,
    detail: str,
) -> None:
    """Persist dynamic_scan_status and dynamic_scan_detail to the DB.

    Opens a dedicated session, commits, and closes.  Failures are logged
    as warnings and never propagate.
    """
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Scan).where(Scan.id == scan_uuid)
            )
            scan = result.scalar_one_or_none()
            if scan:
                scan.dynamic_scan_status = status
                scan.dynamic_scan_detail = detail[:8000] if detail else detail
                await session.commit()
                logger.info(
                    f"Dynamic scan status for {scan_uuid}: "
                    f"{status} — {detail[:120]}"
                )
    except Exception as e:
        logger.warning(
            f"Failed to update dynamic_scan_status for {scan_uuid}: {e}"
        )


# ---------------------------------------------------------------------------
# Sandbox container helpers
# ---------------------------------------------------------------------------

def _build_sandbox_run_cmd(container_name: str) -> list[str]:
    """Build the ``docker run -d`` command with Phase 3a resource limits.

    All three corrections from the post-plan review are applied here:

    CORRECTION 1 — ``--security-opt=no-new-privileges=true``
      Uses equals (``=``) separator, not the deprecated colon (``:``) syntax.
      Colon syntax writes deprecation warnings to stderr, which would
      corrupt container-ID captures if stderr were merged with stdout.

    CORRECTION 2 — ``--network=sandbox_sandbox-net``
      Uses the Compose-prefixed network name as it exists on the host.

    CORRECTION 3 — ``timeout <N> sleep 3600`` entrypoint
      Self-terminating backstop.  ``celery_app.py``'s ``task_time_limit=600``
      sends SIGKILL to the *worker process*, which does NOT guarantee the
      Python ``finally`` block's ``docker rm -f`` executes.  ``timeout``
      gives the container an independent, self-enforced death after
      SANDBOX_TIMEOUT_SECONDS.  The ``finally``-block cleanup remains the
      primary path for the normal case and must NOT be removed.
    """
    return [
        "docker", "run", "-d",
        f"--name={container_name}",
        f"--runtime={SANDBOX_RUNTIME}",
        "--read-only",
        # CORRECTION 2: Compose-prefixed network name
        f"--network={SANDBOX_NETWORK}",
        f"--memory={SANDBOX_MEMORY_LIMIT}",
        f"--memory-swap={SANDBOX_MEMORY_SWAP}",
        f"--cpus={SANDBOX_CPU_LIMIT}",
        f"--pids-limit={SANDBOX_PID_LIMIT}",
        "--cap-drop=ALL",
        # CORRECTION 1: Equals separator (=), not colon (:)
        "--security-opt=no-new-privileges=true",
        f"--tmpfs=/tmp:size={SANDBOX_TMP_SIZE},noexec,nosuid",
        f"--tmpfs=/var/tmp:size={SANDBOX_VAR_TMP_SIZE},noexec,nosuid",
        f"--tmpfs=/workspace:size={SANDBOX_WORKSPACE_SIZE},"
        f"noexec,nosuid,uid=1000,gid=1000",
        # HOME directory fix: container is read_only, pip needs writable $HOME
        "-e", "HOME=/workspace",
        SANDBOX_IMAGE,
        # CORRECTION 3: Self-terminating entrypoint as SIGKILL backstop
        "timeout", str(SANDBOX_TIMEOUT_SECONDS), "sleep", "3600",
    ]


def _run_docker(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a docker CLI command, capturing stdout and stderr separately.

    stderr is always captured into its own stream (never merged with stdout)
    so that deprecation warnings or error messages cannot corrupt parsed
    output like container IDs.  This mirrors the pattern used in
    sandbox/verify_sandbox.sh's FORK_CID/MEM_CID captures.
    """
    logger.debug(f"Docker command: {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        capture_output=True,   # stdout and stderr are separate streams
        text=True,
        timeout=timeout,
    )


def _is_container_running(container_id: str) -> bool:
    """Check if a Docker container is still running."""
    try:
        result = _run_docker(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
            timeout=10,
        )
        return result.stdout.strip().lower() == "true"
    except Exception:
        return False


def _get_container_exit_code(container_id: str) -> int | None:
    """Get the exit code of a stopped container, or None if still running."""
    try:
        result = _run_docker(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", container_id],
            timeout=10,
        )
        return int(result.stdout.strip())
    except Exception:
        return None


def _get_container_logs(container_id: str, tail: int = 50) -> str:
    """Fetch the last N lines of container logs."""
    try:
        result = _run_docker(
            ["docker", "logs", "--tail", str(tail), container_id],
            timeout=10,
        )
        # Combine stdout + stderr from the container (not from docker CLI)
        output = result.stdout + result.stderr
        return output[-MAX_OUTPUT_CHARS:] if len(output) > MAX_OUTPUT_CHARS else output
    except Exception as e:
        return f"(failed to fetch container logs: {e})"


def _check_listening_port(container_id: str) -> int | None:
    """Check for a listening TCP port inside the container via ``ss -tlnp``.

    Does NOT assume a /health endpoint exists — only checks for a bound
    TCP socket.  Returns the first listening port found, or None.
    """
    try:
        result = _run_docker(
            ["docker", "exec", container_id, "ss", "-tlnp"],
            timeout=10,
        )
        # Parse ss output for LISTEN lines.
        # Example line: LISTEN  0  128  0.0.0.0:5000  0.0.0.0:*
        for line in result.stdout.splitlines():
            if "LISTEN" in line:
                match = re.search(r":(\d+)\s", line)
                if match:
                    port = int(match.group(1))
                    # Skip ephemeral/internal ports (only report well-known
                    # web server ports in the typical range)
                    if port > 0:
                        return port
    except Exception as e:
        logger.debug(f"Port check failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _extract_deps_from_pyproject(pyproject_path: str) -> str | None:
    """Extract [project.dependencies] from pyproject.toml.

    Returns requirements.txt-format content, or None if parsing fails or
    no dependencies are declared.

    NOTE: This is a basic parser — it handles PEP 621 ``[project].dependencies``
    but does NOT handle extras, optional-dependencies, or complex version
    specifiers with environment markers.  Most standard projects work fine.
    """
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        deps = data.get("project", {}).get("dependencies", [])
        if deps and isinstance(deps, list):
            return "\n".join(str(d) for d in deps) + "\n"
    except Exception as e:
        logger.warning(f"Failed to parse pyproject.toml: {e}")
    return None


def _truncate_output(text: str) -> str:
    """Truncate to the LAST MAX_OUTPUT_CHARS chars (errors live at the end)."""
    if len(text) > MAX_OUTPUT_CHARS:
        return "…(truncated)…\n" + text[-MAX_OUTPUT_CHARS:]
    return text


# ---------------------------------------------------------------------------
# Entrypoint detection
# ---------------------------------------------------------------------------

def _detect_entrypoint(repo_dir: str) -> tuple[str | None, str]:
    """Detect the app entrypoint at repo root only (no subdirectory search).

    Priority order:
      1. Procfile — parse the ``web:`` line
      2. main.py
      3. app.py

    Returns ``(command, source_description)`` or ``(None, what_was_checked)``.
    """
    # 1. Procfile
    procfile_path = os.path.join(repo_dir, "Procfile")
    if os.path.isfile(procfile_path):
        try:
            with open(procfile_path, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.lower().startswith("web:"):
                        cmd = stripped[4:].strip()
                        if cmd:
                            return cmd, "Procfile web: line"
        except Exception as e:
            logger.warning(f"Failed to read Procfile: {e}")

    # 2. main.py
    if os.path.isfile(os.path.join(repo_dir, "main.py")):
        return "python main.py", "main.py"

    # 3. app.py
    if os.path.isfile(os.path.join(repo_dir, "app.py")):
        return "python app.py", "app.py"

    return (
        None,
        "No entrypoint found (looked for Procfile web: line, main.py, app.py)",
    )


# ---------------------------------------------------------------------------
# Main async pipeline
# ---------------------------------------------------------------------------

async def _run_dynamic_scan(scan_id: str) -> None:
    """Full dynamic scan pipeline — clone, prefetch, sandbox, poll, cleanup."""

    scan_uuid = UUID(scan_id)
    engine, session_factory = _get_task_session()

    # Mutable state for cleanup tracking
    repo_path: str | None = None
    wheels_dir: str | None = None
    container_id: str | None = None

    try:
        # ---- Fetch scan row, verify it exists ----
        async with session_factory() as session:
            result = await session.execute(
                select(Scan).where(Scan.id == scan_uuid)
            )
            scan = result.scalar_one_or_none()
            if not scan:
                logger.error(f"Dynamic scan: scan {scan_id} not found.")
                return
            repo_url = scan.repo_url

        logger.info(f"Dynamic scan starting for {scan_id} ({repo_url})")

        # ================================================================
        # STEP 1: Clone repository (reuse existing repo_handler logic)
        # ================================================================
        try:
            repo_path = clone_repo(repo_url)
        except RuntimeError as e:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "install_failed",
                f"Failed to clone repository: {e}",
            )
            return

        logger.info(f"Dynamic scan: repo cloned to {repo_path}")

        # ================================================================
        # STEP 2: Detect Python manifest
        # ================================================================
        has_requirements = os.path.isfile(
            os.path.join(repo_path, "requirements.txt")
        )
        has_pyproject = os.path.isfile(
            os.path.join(repo_path, "pyproject.toml")
        )

        if not has_requirements and not has_pyproject:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "skipped",
                "No Python dependency manifest found (no requirements.txt "
                "or pyproject.toml at repo root)",
            )
            logger.info(
                f"Dynamic scan: skipped {scan_id} — no Python manifest."
            )
            return

        # If pyproject.toml exists but requirements.txt doesn't, generate a
        # minimal requirements.txt from [project.dependencies]
        requirements_path = os.path.join(repo_path, "requirements.txt")
        if not has_requirements and has_pyproject:
            deps_content = _extract_deps_from_pyproject(
                os.path.join(repo_path, "pyproject.toml")
            )
            if deps_content:
                with open(requirements_path, "w") as f:
                    f.write(deps_content)
                logger.info(
                    "Dynamic scan: generated requirements.txt from "
                    "pyproject.toml [project.dependencies]"
                )
            else:
                await _update_dynamic_status(
                    session_factory, scan_uuid,
                    "skipped",
                    "pyproject.toml found but no [project.dependencies] "
                    "could be extracted",
                )
                return

        # ================================================================
        # STEP 3: Prefetch wheels on worker (outside sandbox, real network)
        # ================================================================
        wheels_dir = tempfile.mkdtemp(prefix="breakmyapp_wheels_")
        logger.info(f"Dynamic scan: prefetching wheels to {wheels_dir}")

        try:
            prefetch_result = subprocess.run(
                [
                    "pip", "download",
                    "-r", requirements_path,
                    "-d", wheels_dir,
                ],
                capture_output=True,
                text=True,
                timeout=180,  # 3 min for downloads
            )
        except subprocess.TimeoutExpired:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "install_failed",
                "Dependency download timed out after 180s",
            )
            return

        if prefetch_result.returncode != 0:
            output = prefetch_result.stdout + prefetch_result.stderr
            # sdist build_requires edge case: pip download may execute build
            # hooks for sdist-only packages.  Treat any download failure as
            # install_failed (fail closed, don't retry inside the sandbox).
            logger.warning(
                f"Dynamic scan: pip download failed (exit {prefetch_result.returncode})"
            )
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "install_failed",
                f"pip download failed (exit {prefetch_result.returncode}):\n"
                + _truncate_output(output),
            )
            return

        logger.info("Dynamic scan: wheels prefetched successfully.")

        # ================================================================
        # STEP 4: Start sandbox container
        # ================================================================
        short_id = scan_id[:8]
        ts = int(time.time())
        container_name = f"sandbox-{short_id}-{ts}"

        run_cmd = _build_sandbox_run_cmd(container_name)
        logger.info(f"Dynamic scan: starting sandbox container {container_name}")

        run_result = _run_docker(run_cmd, timeout=30)

        if run_result.returncode != 0:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "install_failed",
                f"Failed to start sandbox container:\n"
                + _truncate_output(run_result.stderr),
            )
            return

        # Container ID is on stdout (stderr is captured separately,
        # so no risk of corruption — see CORRECTION 1 notes).
        container_id = run_result.stdout.strip()
        logger.info(
            f"Dynamic scan: sandbox container started: {container_id[:12]}"
        )

        # ================================================================
        # STEP 5: Copy repo + wheels into container via docker cp
        # (NOT a bind-mount — uses tmpfs-backed /workspace, capped at
        # SANDBOX_WORKSPACE_SIZE, same containment proven in Phase 3a Test 6)
        # ================================================================
        cp_repo = _run_docker(
            ["docker", "cp", f"{repo_path}/.", f"{container_id}:/workspace/repo"],
            timeout=60,
        )
        if cp_repo.returncode != 0:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "install_failed",
                f"Failed to copy repo into sandbox:\n"
                + _truncate_output(cp_repo.stderr),
            )
            return

        cp_wheels = _run_docker(
            ["docker", "cp", f"{wheels_dir}/.", f"{container_id}:/workspace/wheels"],
            timeout=60,
        )
        if cp_wheels.returncode != 0:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "install_failed",
                f"Failed to copy wheels into sandbox:\n"
                + _truncate_output(cp_wheels.stderr),
            )
            return

        logger.info("Dynamic scan: repo + wheels copied into sandbox.")

        # ================================================================
        # STEP 6: Install dependencies inside sandbox (zero network access)
        # --no-index ensures pip will NOT attempt any network access.
        # ================================================================
        install_result = _run_docker(
            [
                "docker", "exec", container_id,
                "pip", "install",
                "--no-index",
                "--find-links=/workspace/wheels",
                "-r", "/workspace/repo/requirements.txt",
                "--user",       # installs to $HOME/.local (HOME=/workspace)
                "--no-cache-dir",
            ],
            timeout=SANDBOX_TIMEOUT_SECONDS,
        )

        if install_result.returncode != 0:
            output = install_result.stdout + install_result.stderr
            logger.warning(
                f"Dynamic scan: pip install failed "
                f"(exit {install_result.returncode})"
            )
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "install_failed",
                f"pip install failed (exit {install_result.returncode}):\n"
                + _truncate_output(output),
            )
            return

        logger.info("Dynamic scan: dependencies installed inside sandbox.")

        # ================================================================
        # STEP 7: Detect entrypoint
        # ================================================================
        entrypoint_cmd, entrypoint_source = _detect_entrypoint(repo_path)

        if entrypoint_cmd is None:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "start_failed",
                entrypoint_source,   # description of what was checked
            )
            return

        logger.info(
            f"Dynamic scan: entrypoint detected via {entrypoint_source}: "
            f"{entrypoint_cmd}"
        )

        # ================================================================
        # STEP 8: Start app inside sandbox
        # Uses the same container (same resource limits, same sandbox flags).
        # The app runs as a background process inside the already-running
        # container via `docker exec -d`.
        # ================================================================
        # Build the exec command — run from /workspace/repo
        exec_cmd = [
            "docker", "exec", "-d",
            "-w", "/workspace/repo",
            container_id,
            "sh", "-c", entrypoint_cmd,
        ]

        start_result = _run_docker(exec_cmd, timeout=10)
        if start_result.returncode != 0:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "start_failed",
                f"docker exec failed (exit {start_result.returncode}):\n"
                + _truncate_output(start_result.stderr),
            )
            return

        start_time = time.monotonic()
        logger.info("Dynamic scan: app process started, polling for TCP port...")

        # ================================================================
        # STEP 9: Poll for listening TCP port
        # ================================================================
        port_found: int | None = None
        elapsed = 0.0

        while elapsed < STARTUP_POLL_TIMEOUT:
            time.sleep(STARTUP_POLL_INTERVAL)
            elapsed = time.monotonic() - start_time

            # Check if the container is still alive
            if not _is_container_running(container_id):
                exit_code = _get_container_exit_code(container_id)
                logs = _get_container_logs(container_id)
                await _update_dynamic_status(
                    session_factory, scan_uuid,
                    "start_failed",
                    f"Process exited (exit code {exit_code}) before "
                    f"opening a port. Last output:\n{logs}",
                )
                return

            port_found = _check_listening_port(container_id)
            if port_found is not None:
                break

        if port_found is not None:
            bind_time = f"{elapsed:.1f}s"
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "success",
                f"App listening on port {port_found} "
                f"(bound in {bind_time}, entrypoint: {entrypoint_source})",
            )
            logger.info(
                f"Dynamic scan: SUCCESS — port {port_found} bound in "
                f"{bind_time} for scan {scan_id}"
            )
        else:
            # Timeout with process still running but no port
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "start_failed",
                f"No TCP port opened within {STARTUP_POLL_TIMEOUT}s "
                f"(process still running, entrypoint: {entrypoint_source})",
            )
            logger.warning(
                f"Dynamic scan: TIMEOUT — no port opened within "
                f"{STARTUP_POLL_TIMEOUT}s for scan {scan_id}"
            )

    except Exception as e:
        logger.error(f"Dynamic scan unexpected error for {scan_id}: {e}")
        try:
            await _update_dynamic_status(
                session_factory, scan_uuid,
                "start_failed",
                f"Unexpected error: {e}",
            )
        except Exception:
            pass

    finally:
        # ==============================================================
        # CLEANUP — each action wrapped individually so one failure
        # doesn't block the others.
        # ==============================================================

        # 1. Remove sandbox container
        if container_id:
            try:
                _run_docker(
                    ["docker", "rm", "-f", container_id],
                    timeout=15,
                )
                logger.info(
                    f"Dynamic scan: sandbox container {container_id[:12]} removed."
                )
            except Exception as e:
                logger.warning(
                    f"Dynamic scan: failed to remove container "
                    f"{container_id[:12]}: {e}"
                )

        # 2. Clean up cloned repo
        if repo_path:
            try:
                cleanup_repo(repo_path)
            except Exception as e:
                logger.warning(
                    f"Dynamic scan: failed to cleanup repo at {repo_path}: {e}"
                )

        # 3. Clean up prefetched wheels directory
        if wheels_dir:
            try:
                shutil.rmtree(wheels_dir, ignore_errors=True)
                logger.info(f"Dynamic scan: wheels dir {wheels_dir} removed.")
            except Exception as e:
                logger.warning(
                    f"Dynamic scan: failed to cleanup wheels at "
                    f"{wheels_dir}: {e}"
                )

        # 4. Dispose DB engine
        try:
            await engine.dispose()
        except Exception as e:
            logger.warning(f"Dynamic scan: engine dispose failed: {e}")


# ---------------------------------------------------------------------------
# Celery entry point
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="app.tasks.dynamic_scan.run_dynamic_scan")
def run_dynamic_scan(self, scan_id: str) -> None:
    """Celery entry-point — runs the async dynamic scan pipeline."""
    logger.info(f"Starting dynamic scan for scan_id: {scan_id}")
    asyncio.run(_run_dynamic_scan(scan_id))
