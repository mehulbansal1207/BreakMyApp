from celery import Celery
from app.core.config import settings

# Create the Celery instance named "breakmyapp"
celery_app = Celery(
    "breakmyapp",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.analysis", "app.tasks.reaper"]
)

# Apply settings configuration
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Hard limit: SIGKILL after 10 minutes (no Python cleanup possible)
    task_time_limit=600,
    # Soft limit: raises SoftTimeLimitExceeded at 9 minutes
    task_soft_time_limit=540,
    # Recycle worker process after 10 tasks to limit memory leaks
    worker_max_tasks_per_child=10,
    # Acknowledge tasks after execution so crashed workers re-deliver
    task_acks_late=True,
    # Suppress CPendingDeprecationWarning about broker reconnect on startup
    broker_connection_retry_on_startup=True,
    # Sandbox configuration (Phase 3a substrate)
    # Used by the future dynamic scan task to enforce wall-clock timeout
    # and select the gVisor runtime. Config only — no sandbox task yet.
    sandbox_timeout=300,       # Wall-clock SIGKILL timeout in seconds
    sandbox_runtime="runsc",   # Docker runtime for sandboxed containers

    # Periodic task: reap scans stuck at status="running" (worker died)
    beat_schedule={
        "reap-stale-scans": {
            "task": "app.tasks.reaper.reap_stale_scans",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)
