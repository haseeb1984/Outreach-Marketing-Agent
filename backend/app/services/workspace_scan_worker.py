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
from app.services.website_growth_report import build_website_growth_report


async def _guard_allows(guard: Callable[[], Any] | None) -> bool:
    if guard is None:
        return False
    result = guard()
    if inspect.isawaitable(result):
        result = await result
    return result is True


def _safe_count(value: Any) -> int:
    """Normalize untrusted count fields without allowing malformed crawl data to crash jobs."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, min(int(value), 1_000_000))
    except (TypeError, ValueError, OverflowError):
        return 0


def _safe_evidence_urls(value: Any, *, authorized_host: str) -> list[str]:
    """Persist only same-host HTTP(S) evidence without query strings or fragments."""
    if not isinstance(value, list):
        return []
    safe: list[str] = []
    for item in value[:10]:
        if not isinstance(item, str) or not item or len(item) > 2048:
            continue
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in item):
            continue
        try:
            parsed = urlsplit(item)
            _ = parsed.port
        except ValueError:
            continue
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not host
            or host != authorized_host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            continue
        safe.append(item[:512])
        if len(safe) == 3:
            break
    return safe


def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
    """Persist a bounded summary, excluding raw page content and unsafe evidence URLs."""
    discovery = report.get("discovery")
    if not isinstance(discovery, dict):
        discovery = {}
    crawl = discovery.get("crawl")
    if not isinstance(crawl, dict):
        crawl = {}
    findings = crawl.get("aggregate_findings")
    if not isinstance(findings, list):
        findings = []
    authorized_host = str(report.get("authorized_domain", "")).lower().rstrip(".")
    compact_findings = []
    for finding in findings[:10]:
        if not isinstance(finding, dict):
            continue
        compact_findings.append({
            "code": str(finding.get("code", ""))[:80],
            "title": str(finding.get("title", ""))[:120],
            "severity": str(finding.get("severity", ""))[:30],
            "occurrences": _safe_count(finding.get("occurrences", 0)),
            "evidence_urls": _safe_evidence_urls(
                finding.get("evidence_urls"), authorized_host=authorized_host
            ),
        })

    def _list_count(key: str) -> int:
        value = crawl.get(key)
        return len(value) if isinstance(value, list) else 0

    return {
        "authorized_domain": authorized_host[:253],
        "authorization": "verified_domain_record",
        "start_url": str(discovery.get("start_url", ""))[:2048],
        "crawl_skipped": bool(discovery.get("crawl_skipped", False)),
        "pages_crawled": _safe_count(crawl.get("pages_crawled", 0)),
        "aggregate_findings": compact_findings,
        "finding_types_total": len(findings),
        "errors_count": _list_count("errors"),
        "robots_blocked_count": _list_count("robots_blocked_pages"),
        "cross_host_redirects_blocked_count": _list_count("cross_host_redirects_not_crawled"),
        "limitations": [
            "Page-level content and raw HTML are not persisted in the job result.",
            "Evidence URLs with credentials, query strings, fragments, or a different host are omitted.",
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
    max_pages = payload.get("max_pages", 25)
    max_depth = payload.get("max_depth", 2)
    business_type = payload.get("business_type")
    target_market = payload.get("target_market")
    target_queries = payload.get("target_queries")
    growth_context_supplied = any(
        value is not None for value in (business_type, target_market, target_queries)
    )
    growth_context_valid = (
        isinstance(business_type, str) and 1 <= len(business_type.strip()) <= 200
        and isinstance(target_market, str) and 1 <= len(target_market.strip()) <= 200
        and isinstance(target_queries, list) and 1 <= len(target_queries) <= 100
        and all(
            isinstance(query, str) and 1 <= len(query.strip()) <= 200
            and all(char.isprintable() or char == chr(9) for char in query)
            for query in target_queries
        )
        and any(query.strip() for query in target_queries)
    )
    if (
        not isinstance(workspace_id, str) or not workspace_id.strip()
        or not isinstance(start_url, str)
        or isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 100
        or isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 0 <= max_depth <= 5
        or (growth_context_supplied and not growth_context_valid)
    ):
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
            max_pages=max_pages,
            max_depth=max_depth,
        )
        # Produce an evidence-led strategy only when the job explicitly carries
        # business context. Never invent a market or target queries.
        if growth_context_supplied:
            discovery = report.get("discovery")
            if not isinstance(discovery, dict):
                raise ValueError("discovery report is malformed")
            crawl = discovery.get("crawl")
            if not isinstance(crawl, dict):
                raise ValueError("crawl report is malformed")
            report["growth_report"] = build_website_growth_report(
                crawl_report={
                    **crawl,
                    "start_url": discovery.get("start_url", start_url),
                },
                business_type=business_type,
                target_market=target_market,
                target_queries=target_queries,
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
