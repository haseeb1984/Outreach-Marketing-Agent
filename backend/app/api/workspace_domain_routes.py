"""Workspace domain-management endpoints guarded by active membership and role."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_routes import _authenticated, _check_csrf
from app.services.domain_authorization import normalize_domain

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/domains", tags=["workspace domains"])


class DomainChallengeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str = Field(min_length=1, max_length=253)


def _workspace_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    return value


async def _authorize(request: Request, workspace_id: str, minimum_role: str) -> tuple[Any, dict]:
    store, _, session = await _authenticated(request)
    workspace_id = _workspace_id(workspace_id)
    try:
        allowed = await store.authorize_workspace(
            user_id=session["user_id"],
            workspace_id=workspace_id,
            minimum_role=minimum_role,
        )
    except Exception:
        # Fail closed without exposing database or provider details.
        raise HTTPException(status_code=503, detail="workspace_authorization_unavailable") from None
    if not allowed:
        # Same response for missing workspace and non-members to reduce enumeration.
        raise HTTPException(status_code=404, detail="workspace_not_found")
    domain_store = getattr(request.app.state, "domain_authorization_store", None)
    if domain_store is None:
        raise HTTPException(status_code=503, detail="workspace_domains_unavailable")
    return domain_store, session


@router.get("")
async def list_verified_domains(workspace_id: str, request: Request):
    domain_store, _ = await _authorize(request, workspace_id, "viewer")
    try:
        domains = await domain_store.get_verified_domains(workspace_id=workspace_id)
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_domains_unavailable") from None
    return {
        "workspace_id": workspace_id,
        "domains": [
            {
                "domain": row["domain"],
                "status": row["status"],
                "verified_at": row["verified_at"].isoformat() if row.get("verified_at") else None,
            }
            for row in domains
        ],
    }


@router.post("/challenges", status_code=201)
async def create_domain_challenge(
    workspace_id: str, payload: DomainChallengeInput, request: Request
):
    domain_store, session = await _authorize(request, workspace_id, "admin")
    _check_csrf(request, session)
    try:
        result = await domain_store.issue_challenge(
            workspace_id=workspace_id, domain=normalize_domain(payload.domain)
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_domain") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_challenge_unavailable") from None
    challenge = result["challenge"]
    dns_record = result["dns_record"]
    return {
        "workspace_id": workspace_id,
        "domain": challenge["domain"],
        "method": challenge["method"],
        "txt_record_name": dns_record["record_name"],
        "txt_record_value": dns_record["record_value"],
        "expires_at": challenge["expires_at"],
    }


@router.delete("/{domain}")
async def revoke_verified_domain(workspace_id: str, domain: str, request: Request):
    domain_store, session = await _authorize(request, workspace_id, "admin")
    _check_csrf(request, session)
    try:
        normalized = normalize_domain(domain)
        revoked = await domain_store.revoke_domain(
            workspace_id=workspace_id, domain=normalized
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_domain") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_revocation_unavailable") from None
    if not revoked:
        raise HTTPException(status_code=404, detail="verified_domain_not_found")
    return {"workspace_id": workspace_id, "domain": normalized, "status": "revoked"}
