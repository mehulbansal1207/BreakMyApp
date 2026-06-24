import asyncio
import logging
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.celery_app import celery_app
from app.core.config import settings
from app.models.scan import Scan
from app.services.repo_handler import clone_repo, cleanup_repo, get_repo_info
from app.services.scanners.secrets_scanner import scan_secrets
from app.services.scanners.semgrep_scanner import scan_semgrep
from app.services.scanners.bandit_scanner import scan_bandit
from app.services.scanners.dependency_scanner import scan_dependencies
from app.services.ai_explainer import explain_findings
from app.services.minio_service import upload_scan_artifacts
from app.services.webhook_service import fire_webhook, build_webhook_payload


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_task_session():
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False
    )
    return engine, session_factory


async def _run_full_analysis(scan_id: str) -> None:
    scan_uuid = UUID(scan_id)
    repo_path = None
    callback_url = None
    engine, session_factory = get_task_session()

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Scan).where(Scan.id == scan_uuid)
            )
            scan = result.scalar_one_or_none()
            if not scan:
                logger.error(f"Scan {scan_id} not found.")
                return
            repo_url = scan.repo_url
            callback_url = scan.callback_url
            scan.status = "running"
            await session.commit()
            logger.info(f"Scan {scan_id} status set to running.")

        findings = {}
        score = 0
        status = "completed"

        try:
            repo_path = clone_repo(repo_url)
            repo_info = get_repo_info(repo_path)
            secrets = scan_secrets(repo_path)
            semgrep = scan_semgrep(repo_path)
            bandit = scan_bandit(repo_path)
            dependencies = scan_dependencies(repo_path)

            findings = {
                "repo_info": repo_info,
                "secrets": secrets,
                "semgrep": semgrep,
                "bandit": bandit,
                "dependencies": dependencies
            }

            score = 100
            for finding in secrets.get("findings", []):
                severity = finding.get("severity", "")
                if severity == "CRITICAL":
                    score -= 20
                elif severity == "HIGH":
                    score -= 10
                elif severity == "MEDIUM":
                    score -= 5

            for finding in semgrep.get("findings", []):
                severity = finding.get("severity", "")
                if severity == "HIGH":
                    score -= 10
                elif severity == "MEDIUM":
                    score -= 5
                elif severity == "LOW":
                    score -= 2

            for finding in bandit.get("findings", []):
                severity = finding.get("severity", "")
                if severity == "HIGH":
                    score -= 10
                elif severity == "MEDIUM":
                    score -= 5
                elif severity == "LOW":
                    score -= 2

            for finding in dependencies.get("findings", []):
                severity = finding.get("severity", "")
                if severity == "CRITICAL":
                    score -= 20
                elif severity == "HIGH":
                    score -= 10
                elif severity == "MEDIUM":
                    score -= 5
                elif severity == "LOW":
                    score -= 2

            score = max(0, score)

            ai_explanation = explain_findings(findings, score)
            findings["ai_explanation"] = ai_explanation

            # Upload raw scanner artifacts to MinIO (non-blocking — failure does not affect scan)
            try:
                uploaded = upload_scan_artifacts(scan_id, {
                    "secrets": secrets,
                    "semgrep": semgrep,
                    "bandit": bandit,
                    "dependencies": dependencies,
                })
                if uploaded:
                    logger.info(f"Artifacts uploaded to MinIO for scan {scan_id}")
                else:
                    logger.warning(f"MinIO upload skipped or failed for scan {scan_id}")
            except Exception as e:
                logger.warning(f"MinIO upload error for scan {scan_id}: {e}")

        except RuntimeError as e:
            logger.error(f"Analysis failed for scan {scan_id}: {e}")
            findings = {"error": str(e)}
            score = 0
            status = "failed"
        except Exception as e:
            logger.error(f"Unexpected error for scan {scan_id}: {e}")
            findings = {"error": str(e)}
            score = 0
            status = "failed"
        finally:
            if repo_path:
                cleanup_repo(repo_path)

        async with session_factory() as session:
            result = await session.execute(
                select(Scan).where(Scan.id == scan_uuid)
            )
            scan = result.scalar_one_or_none()
            if scan:
                scan.findings = findings
                scan.score = score
                scan.status = status
                await session.commit()
                logger.info(
                    f"Scan {scan_id} saved with status={status} score={score}."
                )

                # Fire webhook if callback_url was provided
                if callback_url:
                    try:
                        payload = build_webhook_payload(scan_id, scan)
                        success = fire_webhook(scan_id, callback_url, payload)
                        if success:
                            logger.info(f"Webhook fired successfully for scan {scan_id}")
                        else:
                            logger.warning(f"Webhook failed for scan {scan_id} to {callback_url}")
                    except Exception as e:
                        logger.warning(f"Webhook error for scan {scan_id}: {e}")

    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="app.tasks.analysis.run_analysis")
def run_analysis(self, scan_id: str) -> None:
    logger.info(f"Starting analysis for scan_id: {scan_id}")
    asyncio.run(_run_full_analysis(scan_id))