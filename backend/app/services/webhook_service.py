import json
import logging
import time
import datetime
import ipaddress
import socket
import urllib.parse
from typing import Any

import requests

logger = logging.getLogger(__name__)


def build_webhook_payload(scan_id: str, scan: Any) -> dict:
    """
    Build the webhook POST body from a completed scan object.
    scan is a SQLAlchemy Scan model instance.
    """
    findings: dict = scan.findings or {}
    ai: dict = findings.get("ai_explanation", {})

    return {
        "event": "scan.completed",
        "scan_id": str(scan.id),
        "repo_url": scan.repo_url,
        "status": scan.status,
        "score": scan.score,
        "report_url": f"https://breakmyapp.tech/scan/{scan.id}",
        "findings_summary": {
            "secrets": findings.get("secrets", {}).get("findings_count", 0),
            "security": findings.get("semgrep", {}).get("findings_count", 0),
            "code_quality": findings.get("bandit", {}).get("findings_count", 0),
            "dependencies": findings.get("dependencies", {}).get("findings_count", 0),
        },
        "top_priorities": ai.get("top_priorities", [])[:3] if ai else [],
        "executive_summary": ai.get("executive_summary", "") if ai else "",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


def _is_safe_callback_url(url: str) -> tuple[bool, str, list[str]]:
    """
    Validate that a callback URL is safe to send a request to.

    Returns (True, "", [safe_ips]) if the URL is safe, or (False, reason, []) if it should
    be rejected.  Fail-closed: any resolution error or ambiguity is treated
    as unsafe.
    """
    # -- Scheme check --
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return False, f"scheme must be https, got '{parsed.scheme}'", []

    hostname = parsed.hostname
    if not hostname:
        return False, "missing hostname", []

    # -- DNS resolution --
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        return False, f"DNS resolution failed for '{hostname}': {exc}", []

    if not addr_infos:
        return False, f"DNS resolution returned no addresses for '{hostname}'", []

    safe_ips = []
    # -- IP safety checks --
    for addr_info in addr_infos:
        raw_ip = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            return False, f"could not parse resolved IP '{raw_ip}'", []

        # Unwrap IPv4-mapped IPv6 addresses (::ffff:x.x.x.x) before checking —
        # otherwise an attacker can return an AAAA record wrapping a private/
        # link-local IPv4 address (e.g. ::ffff:169.254.169.254) and bypass
        # every check below, since ipaddress.IPv6Address does NOT recurse
        # into the embedded IPv4 address for .is_private/.is_link_local/etc.
        candidates = [ip]
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            candidates.append(mapped)

        for candidate in candidates:
            if candidate.is_private:
                return False, f"resolved IP {raw_ip} maps to private range ({candidate})", []
            if candidate.is_loopback:
                return False, f"resolved IP {raw_ip} maps to loopback ({candidate})", []
            if candidate.is_link_local:
                return False, f"resolved IP {raw_ip} maps to link-local ({candidate})", []
            if candidate.is_reserved:
                return False, f"resolved IP {raw_ip} maps to reserved range ({candidate})", []
            if candidate.is_multicast:
                return False, f"resolved IP {raw_ip} maps to multicast ({candidate})", []
            if candidate.is_unspecified:
                return False, f"resolved IP {raw_ip} maps to unspecified ({candidate})", []

        if raw_ip not in safe_ips:
            safe_ips.append(raw_ip)

    return True, "", safe_ips


def fire_webhook(scan_id: str, callback_url: str, payload: dict) -> bool:
    """
    POST payload as JSON to callback_url.
    Retries up to 3 times with 2s delay between attempts.
    Timeout: 10s per attempt.
    Returns True if any attempt succeeds (2xx response).
    Returns False if all attempts fail.
    Never raises — all exceptions caught internally.
    """
    # -- SSRF protection: validate callback URL before any request --
    #
    # WHY IP PINNING IS NECESSARY (DNS rebinding / TOCTOU):
    # If we only validate the hostname and then pass it to requests.post(),
    # requests/urllib3 will perform its own DNS resolution at connect time.
    # An attacker could use DNS rebinding: return a safe public IP during
    # the validation phase (above), then return a malicious internal IP
    # (e.g. 169.254.169.254) when requests.post() resolves a few ms later.
    # To prevent this, we capture the exact IPs we validated and force
    # socket.getaddrinfo to return ONLY those IPs during the actual request,
    # completely bypassing any second DNS lookup.
    safe, reason, safe_ips = _is_safe_callback_url(callback_url)
    if not safe:
        logger.error(
            "Webhook callback URL rejected for scan %s — SSRF protection: %s. URL: %s",
            scan_id,
            reason,
            callback_url,
        )
        return False

    max_attempts: int = 3
    pinned_ip = safe_ips[0]

    def _pinned_getaddrinfo(host, port=None, *args, **kwargs):
        # Forward the real requested port instead of discarding it —
        # hardcoding port 0 here would make every connection attempt
        # fail regardless of which IP is pinned, masking the real test.
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (pinned_ip, port or 443))]

    for attempt in range(1, max_attempts + 1):
        # CONCURRENCY WARNING: This monkeypatch of socket.getaddrinfo is
        # process-global while active. It is only safe because the Celery
        # worker currently runs with --concurrency=1 (single-threaded
        # execution per worker process). If worker concurrency is ever
        # increased above 1, this mechanism would need to be replaced with
        # a per-thread resolution override or a proper IP-pinning library
        # to avoid a race condition between concurrent webhook deliveries.
        original_getaddrinfo = socket.getaddrinfo
        try:
            socket.getaddrinfo = _pinned_getaddrinfo
            try:
                response = requests.post(
                    callback_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "BreakMyApp-Webhook/1.0",
                    },
                    timeout=10,
                    allow_redirects=False,
                )
            finally:
                socket.getaddrinfo = original_getaddrinfo

            if 200 <= response.status_code <= 299:
                logger.info(
                    "Webhook delivered successfully for scan %s to %s (attempt %d, status %d).",
                    scan_id,
                    callback_url,
                    attempt,
                    response.status_code,
                )
                return True
            elif 300 <= response.status_code <= 399:
                logger.warning(
                    "Webhook attempt %d for scan %s returned redirect status %d — "
                    "redirects are not followed for security reasons.",
                    attempt,
                    scan_id,
                    response.status_code,
                )
            else:
                logger.warning(
                    "Webhook attempt %d for scan %s returned non-2xx status %d.",
                    attempt,
                    scan_id,
                    response.status_code,
                )
        except requests.RequestException as exc:
            logger.warning(
                "Webhook attempt %d for scan %s failed: %s.",
                attempt,
                scan_id,
                exc,
            )
        finally:
            # Belt-and-suspenders: ensure getaddrinfo is always restored even
            # if an unexpected exception type bypasses the inner finally.
            socket.getaddrinfo = original_getaddrinfo

        if attempt < max_attempts:
            time.sleep(2)

    logger.error(
        "All %d webhook attempts exhausted for scan %s. Callback URL: %s.",
        max_attempts,
        scan_id,
        callback_url,
    )
    return False
