"""Workspace-admin DNS TXT verification for authorized client websites."""
from __future__ import annotations

import asyncio
import dns.exception
import dns.resolver
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1/domains", tags=["domain authorization"])


class DomainChallengeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=3, max_length=253)


class DomainVerificationInput(DomainChallengeInput):
    pass


async def _authorize_admin(request: Request, workspace_id: str) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="admin"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    return session


def _store(request: Request):
    store = getattr(request.app.state, "domain_authorization_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="domain_authorization_not_configured")
    return store


def _resolve_txt(domain: str) -> list[str]:
    answer = dns.resolver.resolve(
        "_oma-verify." + domain,
        "TXT",
        lifetime=4.0,
        search=False,
    )
    values: list[str] = []
    for record in answer:
        chunks = getattr(record, "strings", None)
        if chunks:
            try:
                values.append(b"".join(chunks).decode("utf-8"))
            except UnicodeDecodeError:
                continue
        else:
            values.append(record.to_text().strip('"'))
    return values


@router.get("")
async def list_verified_domains(request: Request, workspace_id: str) -> dict:
    await _authorize_admin(request, workspace_id)
    try:
        items = await _store(request).get_verified_domains(workspace_id=workspace_id)
    except Exception:
        raise HTTPException(status_code=503, detail="domain_list_unavailable") from None
    return {"items": items}


@router.post("/challenges", status_code=201)
async def create_domain_challenge(payload: DomainChallengeInput, request: Request) -> dict:
    await _authorize_admin(request, payload.workspace_id)
    try:
        issued = await _store(request).issue_challenge(
            workspace_id=payload.workspace_id, domain=payload.domain
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_domain") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_challenge_unavailable") from None
    challenge = issued["challenge"]
    return {
        "workspace_id": payload.workspace_id,
        "domain": challenge["domain"],
        "method": "dns_txt",
        "expires_at": challenge["expires_at"],
        "dns_record": issued["dns_record"],
        "instructions": "Add this TXT record to your domain DNS. Verification checks public DNS directly; do not submit a value manually as proof.",
    }


@router.post("/verify")
async def verify_domain(payload: DomainVerificationInput, request: Request) -> dict:
    await _authorize_admin(request, payload.workspace_id)
    try:
        challenge = await _store(request).get_pending_challenge(
            workspace_id=payload.workspace_id, domain=payload.domain
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_domain") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_challenge_unavailable") from None
    if challenge is None:
        raise HTTPException(status_code=404, detail="pending_domain_challenge_not_found")
    try:
        txt_values = await asyncio.to_thread(_resolve_txt, challenge["domain"])
    except (dns.exception.DNSException, OSError, ValueError):
        raise HTTPException(status_code=422, detail="domain_txt_record_not_found") from None
    try:
        result = await _store(request).verify_challenge(
            workspace_id=payload.workspace_id,
            domain=payload.domain,
            txt_values=txt_values,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="domain_verification_input_invalid") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_verification_unavailable") from None
    if not result.get("verified"):
        reason = result.get("reason", "domain_verification_failed")
        status_code = 410 if reason == "challenge_expired" else 422
        raise HTTPException(status_code=status_code, detail=reason)
    return {"workspace_id": payload.workspace_id, "domain": challenge["domain"], "verified": True}


@router.delete("/{domain}")
async def revoke_domain(domain: str, request: Request, workspace_id: str) -> dict:
    await _authorize_admin(request, workspace_id)
    try:
        revoked = await _store(request).revoke_domain(workspace_id=workspace_id, domain=domain)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_domain") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_revocation_unavailable") from None
    if not revoked:
        raise HTTPException(status_code=404, detail="verified_domain_not_found")
    return {"workspace_id": workspace_id, "domain": domain, "revoked": True}
