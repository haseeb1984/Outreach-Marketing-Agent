"""Worker orchestration for verified-domain website scans.

This module has no public route. A production worker must inject an egress guard
that confirms connection-time destination pinning is active; absent/failed guards
cause the job to fail closed before any target request.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable
from urllib.parse import urlsplit

from app.services.authorized_website_discovery import discover_authorized_website


async def _guard_allows(guard: Callable[[], Any] | None) -> bool:
    if guard is None:
        return False
    result = guard()
    if inspect.isawaitable(result):
        result = await result
    return result is True


def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
    """Persist a bounded summary, not the full page-level report or raw page content."""
    discovery = report.get("discovery") or {}
    crawl = discovery.get("crawl") or {}
    findings = crawl.get("aggregate_findings") or []
    compact_findings = []
    for finding in findings[:50]:
        if not isinstance(finding, dict):
            continue
        compact_findings.append({
            "code": str(finding.get("code", ""))[:100],
            "title": str(finding.get("title", ""))[:200],
            "severity": str(finding.get("severity", ""))[:30],
            "occurrences": max(0, int(finding.get("occurrences", 0))),
            "evidence_urls": [
                str(url)[:2048] for url in (finding.get("evidence_urls") or [])[:10]
                if isinstance(url, str)
            ],
        })
    return {
        "authorized_domain": str(report.get("authorized_domain", ""))[:253],
        "authorization": "verified_domain_record",
        "start_url": str(discovery.get("start_url", ""))[:2048],
        "crawl_skipped": bool(discovery.get("crawl_skipped", False)),
        "pages_crawled": max(0, int(crawl.get("pages_crawled", 0))),
        "aggregate_findings": compact_findings,
        "finding_types_total": len(findings),
        "errors_count": len(crawl.get("errors") or []),
        "robots_blocked_count": len(crawl.get("robots_blocked_pages") or []),
        "cross_host_redirects_blocked_count": len(crawl.get("cross_host_redirects_not_crawled") or []),
        "limitations": [
            "Page-level content and raw HTML are not persisted in the job result.",
            "This summary is based on a bounded source-HTML crawl.",
        ],
    }


async def process_claimed_website_scan(
    *,
    job: dict[str, Any],
    worker_id: str,
    domain_store: Any,
    job_queue: Any,
    egress_guard: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run one already-claimed job, rechecking current authorization before fetching."""
    job_id = job.get("id")
    workspace_id = job.get("workspace_id")
    payload = job.get("payload")
    if job.get("job_type") != "website_growth_scan" or not isinstance(payload, dict):
        status = await job_queue.fail(
            job_id=job_id, worker_id=worker_id, error_code="invalid_scan_job"
        )
        return {"status": status, "reason": "invalid_scan_job"}
    start_url = payload.get("start_url")
    if not isinstance(workspace_id, str) or not workspace_id.strip() or not isinstance(start_url, str):
        status = await job_queue.fail(
            job_id=job_id, worker_id=worker_id, error_code="invalid_scan_job"
        )
        return {"status": status, "reason": "invalid_scan_job"}

    try:
        authorization = await domain_store.authorize_url(
            workspace_id=workspace_id,
            url=start_url,
        )
        if str(authorization.get("workspace_id")) != workspace_id:
            raise PermissionError("workspace authorization mismatch")
        authorized_host = str(authorization.get("host", "")).lower().rstrip(".")
        payload_host = str(payload.get("authorized_domain", "")).lower().rstrip(".")
        current_host = (urlsplit(authorization.get("url", "")).hostname or "").lower().rstrip(".")
        if not authorized_host or authorized_host != payload_host or current_host != authorized_host:
            raise PermissionError("verified domain no longer matches scan job")
    except Exception:
        status = await job_queue.fail(
            job_id=job_id, worker_id=worker_id, error_code="domain_authorization_failed"
        )
        return {"status": status, "reason": "domain_authorization_failed"}

    try:
        egress_allowed = await _guard_allows(egress_guard)
    except Exception:
        egress_allowed = False
    if not egress_allowed:
        status = await job_queue.fail(
            job_id=job_id, worker_id=worker_id, error_code="egress_policy_unavailable"
        )
        return {"status": status, "reason": "egress_policy_unavailable"}

    try:
        report = await discover_authorized_website(
            store=domain_store,
            workspace_id=workspace_id,
            start_url=start_url,
            max_pages=payload.get("max_pages", 25),
            max_depth=payload.get("max_depth", 2),
        )
        completed = await job_queue.complete(
            job_id=job_id,
            worker_id=worker_id,
            result=_compact_report(report),
        )
    except Exception:
        status = await job_queue.fail(
            job_id=job_id, worker_id=worker_id, error_code="website_scan_failed"
        )
        return {"status": status, "reason": "website_scan_failed"}
    if not completed:
        return {"status": "lease_lost", "reason": "job_lease_no_longer_owned"}
    return {"status": "succeeded", "job_id": str(job_id)}
