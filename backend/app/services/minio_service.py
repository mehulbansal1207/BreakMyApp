import io
import json
import logging
import datetime

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)

BUCKET_NAME = "breakmyapp-artifacts"


def get_minio_client() -> Minio:
    """Return a configured Minio client (fresh per call, no TLS)."""
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=True,
    )


def ensure_bucket_exists(client: Minio) -> None:
    """Create BUCKET_NAME if it does not already exist."""
    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)
        logger.info("Created MinIO bucket: %s", BUCKET_NAME)


def upload_scan_artifacts(scan_id: str, findings: dict) -> bool:
    """
    Upload raw scanner JSON outputs to MinIO.
    Returns True if successful, False if any error occurs.
    Never raises — caller should log and continue.
    """
    artifact_keys = {
        "secrets": f"{scan_id}/secrets.json",
        "semgrep": f"{scan_id}/semgrep.json",
        "bandit": f"{scan_id}/bandit.json",
        "dependencies": f"{scan_id}/dependencies.json",
    }

    try:
        client = get_minio_client()
        ensure_bucket_exists(client)

        for finding_key, object_name in artifact_keys.items():
            data_bytes = json.dumps(findings[finding_key]).encode("utf-8")
            data_stream = io.BytesIO(data_bytes)
            client.put_object(
                BUCKET_NAME,
                object_name,
                data_stream,
                length=len(data_bytes),
                content_type="application/json",
            )
            logger.debug("Uploaded %s to MinIO bucket %s", object_name, BUCKET_NAME)

        return True

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to upload scan artifacts for scan_id=%s: %s",
            scan_id,
            exc,
        )
        return False


def get_artifact_urls(scan_id: str) -> dict | None:
    """
    Returns presigned download URLs for all 4 artifacts.
    Returns None if artifacts don't exist or MinIO is unreachable.
    Never raises.
    """
    artifact_keys = {
        "secrets": f"{scan_id}/secrets.json",
        "semgrep": f"{scan_id}/semgrep.json",
        "bandit": f"{scan_id}/bandit.json",
        "dependencies": f"{scan_id}/dependencies.json",
    }

    try:
        client = get_minio_client()

        # Verify at least the first artifact exists before generating URLs.
        try:
            client.stat_object(BUCKET_NAME, artifact_keys["secrets"])
        except S3Error:
            return None

        expiry = datetime.timedelta(hours=1)
        urls: dict[str, str] = {}
        for finding_key, object_name in artifact_keys.items():
            url = client.presigned_get_object(BUCKET_NAME, object_name, expires=expiry)
            urls[finding_key] = url

        return urls

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to retrieve artifact URLs for scan_id=%s: %s",
            scan_id,
            exc,
        )
        return None
