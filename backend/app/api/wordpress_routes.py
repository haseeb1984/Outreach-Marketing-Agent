"""Workspace-scoped WordPress connection and human-gated article delivery."""
from __future__ import annotations

import base64
import ipaddress
import os
import re
from html import escape
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import dns.asyncresolver
import dns.exception
import dns.resolver
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings

router = APIRouter(prefix="/api/v1/integrations/wordpress", tags=["WordPress"])
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".test")


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="wordpress_service_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, role: str, session: dict) -> None:
    auth = getattr(request.app.state, "auth_store", None)
    if auth is None or not await auth.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")


def _key() -> bytes:
    value = settings.provider_credential_encryption_key
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured")
    try:
        raw = base64.b64decode(value.strip() + "=" * (-len(value.strip()) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured") from None
    if len(raw) != 32:
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured")
    return raw


def _aad(workspace_id: str, connection_id: UUID) -> bytes:
    return ("workspace-wordpress-connection:" + workspace_id + ":" + str(connection_id)).encode()


def _encrypt(value: str, workspace_id: str, connection_id: UUID) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, value.encode(), _aad(workspace_id, connection_id))


def _decrypt(ciphertext: bytes, workspace_id: str, connection_id: UUID) -> str:
    raw = bytes(ciphertext)
    if len(raw) < 29:
        raise HTTPException(status_code=503, detail="wordpress_credential_decryption_failed")
    try:
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], _aad(workspace_id, connection_id)).decode()
    except Exception:
        raise HTTPException(status_code=503, detail="wordpress_credential_decryption_failed") from None


def _site_url(value: str) -> str:
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
        except ValueError:
            address = None
    except ValueError:
        raise ValueError("wordpress_site_url_invalid") from None
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
            or port not in (None, 443) or parsed.query or parsed.fragment
            or any(host.endswith(suffix) or host == suffix[1:] for suffix in _LOCAL_SUFFIXES)
            or host in {"localhost", "metadata.google.internal"}):
        raise ValueError("wordpress_site_must_be_public_https")
    if address is not None and (not address.is_global):
        raise ValueError("wordpress_site_must_be_public_https")
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        raise ValueError("wordpress_site_host_invalid")
    return value


def _safe_post_link(site_url: str, candidate: object) -> str | None:
    if not isinstance(candidate, str) or len(candidate) > 4096:
        return None
    try:
        base = urlsplit(site_url)
        link = urlsplit(candidate)
        if (link.scheme != "https" or link.hostname != base.hostname
                or link.port not in (None, 443) or link.username or link.password
                or not link.path.startswith("/")):
            return None
    except ValueError:
        return None
    return candidate


def _html_from_markdown(markdown: str) -> str:
    """Small safe Markdown subset; all text is escaped and raw HTML is never passed through."""
    output: list[str] = []
    paragraph: list[str] = []
    in_list = False

    def inline(value: str) -> str:
        safe = escape(value, quote=False)
        safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
        safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", safe)
        safe = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", safe)
        return safe

    def flush_paragraph() -> None:
        if paragraph:
            output.append("<p>" + "<br>".join(inline(line) for line in paragraph) + "</p>")
            paragraph.clear()

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            flush_paragraph()
            if in_list:
                output.append("</ul>")
                in_list = False
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            if in_list:
                output.append("</ul>")
                in_list = False
            level = len(heading.group(1)) + 1
            output.append(f"<h{level}>" + inline(heading.group(2)) + f"</h{level}>")
        elif line.startswith("- ") or line.startswith("* "):
            flush_paragraph()
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append("<li>" + inline(line[2:]) + "</li>")
        else:
            if in_list:
                output.append("</ul>")
                in_list = False
            paragraph.append(line)
    flush_paragraph()
    if in_list:
        output.append("</ul>")
    return "\n".join(output)


async def _ensure_public_dns(host: str) -> None:
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise HTTPException(status_code=422, detail="wordpress_site_must_be_public_https")
        return
    except ValueError:
        pass
    resolver = dns.asyncresolver.Resolver()
    addresses: list[str] = []
    for record_type in ("A", "AAAA"):
        try:
            answer = await resolver.resolve(host, record_type, lifetime=3.0)
            addresses.extend(item.address for item in answer)
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.exception.DNSException:
            raise HTTPException(status_code=502, detail="wordpress_site_dns_unavailable") from None
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise HTTPException(status_code=422, detail="wordpress_site_must_resolve_to_public_addresses")


async def _request(site_url: str, username: str, password: str, method: str, path: str, **kwargs):
    host = urlsplit(site_url).hostname or ""
    await _ensure_public_dns(host)
    url = site_url + "/wp-json/wp/v2/" + path.lstrip("/")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False,
            trust_env=False, auth=(username, password),
        ) as client:
            response = await client.request(method, url, **kwargs)
        return response
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="wordpress_provider_unavailable") from None


class WordPressConnect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    site_url: str = Field(min_length=10, max_length=2048)
    username: str = Field(min_length=1, max_length=200)
    application_password: str = Field(min_length=8, max_length=512)

    @field_validator("site_url")
    @classmethod
    def validate_site(cls, value: str) -> str:
        return _site_url(value)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(ch) < 32 for ch in value):
            raise ValueError("wordpress_username_invalid")
        return value

    @field_validator("application_password")
    @classmethod
    def clean_password(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 8 or any(ord(ch) < 32 for ch in value):
            raise ValueError("wordpress_application_password_invalid")
        return value


class WordPressPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    confirm_publish: bool = False


@router.get("/connection")
async def get_connection(request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id,site_url,username,status,verified_at,created_at,updated_at
                   FROM workspace_wordpress_connections WHERE workspace_id=$1""", workspace_id
            )
        if row is None:
            return {"connected": False}
        item = dict(row)
        item["id"] = str(item["id"])
        return {"connected": True, "connection": item}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="wordpress_connection_unavailable") from None


@router.put("/connection")
async def save_connection(payload: WordPressConnect, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    connection_id = uuid4()
    encrypted = _encrypt(payload.application_password, payload.workspace_id, connection_id)
    try:
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchval(
                    "SELECT id FROM workspace_wordpress_connections WHERE workspace_id=$1 FOR UPDATE",
                    payload.workspace_id,
                )
                if existing:
                    connection_id = existing
                    encrypted = _encrypt(payload.application_password, payload.workspace_id, connection_id)
                    await conn.execute(
                        """UPDATE workspace_wordpress_connections SET site_url=$2,username=$3,
                                  encrypted_application_password=$4,status='pending',
                                  verified_at=NULL,updated_at=now() WHERE id=$1""",
                        connection_id, payload.site_url, payload.username, encrypted,
                    )
                else:
                    await conn.execute(
                        """INSERT INTO workspace_wordpress_connections
                           (id,workspace_id,site_url,username,encrypted_application_password,created_by)
                           VALUES ($1,$2,$3,$4,$5,$6)""",
                        connection_id,payload.workspace_id,payload.site_url,payload.username,
                        encrypted,UUID(str(session["user_id"])),
                    )
        return {"saved": True, "connection_id": str(connection_id),
                "status": "pending", "notice": "Credentials encrypted. Verify the connection before sending drafts."}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="wordpress_connection_save_unavailable") from None


@router.post("/connection/verify")
async def verify_connection(request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id,site_url,username,encrypted_application_password,status
                   FROM workspace_wordpress_connections WHERE workspace_id=$1""", workspace_id
            )
        if row is None:
            raise HTTPException(status_code=404, detail="wordpress_connection_not_found")
        if row["status"] == "disabled" or row["encrypted_application_password"] is None:
            raise HTTPException(status_code=409, detail="wordpress_connection_credentials_revoked")
        connection_id = row["id"]
        password = _decrypt(row["encrypted_application_password"], workspace_id, connection_id)
        response = await _request(row["site_url"], row["username"], password, "GET", "users/me",
                                  params={"context": "edit"})
        if response.status_code != 200:
            raise HTTPException(status_code=422, detail="wordpress_authentication_failed")
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            raise HTTPException(status_code=502, detail="wordpress_identity_response_invalid")
        capabilities = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
        if capabilities.get("edit_posts") is not True or capabilities.get("publish_posts") is not True:
            raise HTTPException(status_code=422, detail="wordpress_user_lacks_post_capabilities")
        async with _pool(request).acquire() as conn:
            await conn.execute(
                """UPDATE workspace_wordpress_connections SET status='verified',
                          verified_at=now(),updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND encrypted_application_password=$3""",
                connection_id,workspace_id,row["encrypted_application_password"],
            )
        return {"verified": True, "username": str(data.get("slug") or row["username"]),
                "status": "verified"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="wordpress_verification_unavailable") from None


@router.delete("/connection")
async def disconnect(request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE workspace_wordpress_connections
                   SET status='disabled',encrypted_application_password=NULL,
                       verified_at=NULL,updated_at=now()
                   WHERE workspace_id=$1 AND status <> 'disabled'
                   RETURNING id""",
                workspace_id,
            )
        return {"disconnected": row is not None, "credentials_revoked": row is not None}
    except Exception:
        raise HTTPException(status_code=503, detail="wordpress_disconnect_unavailable") from None


@router.post("/articles/{brief_id}/send-draft")
async def send_article_as_draft(brief_id: UUID, request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    delivery_claimed = False
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """SELECT b.article_title,b.meta_title,b.meta_description,b.article_body,
                          b.article_status,b.cms_status,b.cms_post_id,c.id AS connection_id,
                          c.site_url,c.username,c.encrypted_application_password
                   FROM website_content_briefs b
                   JOIN workspace_wordpress_connections c
                     ON c.workspace_id=b.workspace_id AND c.status='verified'
                   WHERE b.id=$1 AND b.workspace_id=$2""", brief_id, workspace_id
            )
        if row is None:
            raise HTTPException(status_code=404, detail="wordpress_article_or_connection_not_found")
        if row["article_status"] != "approved":
            raise HTTPException(status_code=409, detail="article_editorial_approval_required")
        if row["cms_status"] == "draft_created":
            raise HTTPException(status_code=409, detail="wordpress_draft_already_created")
        if row["cms_status"] == "published":
            raise HTTPException(status_code=409, detail="wordpress_article_already_published")
        connection_id = row["connection_id"]
        password = _decrypt(row["encrypted_application_password"],workspace_id,connection_id)
        async with _pool(request).acquire() as conn:
            claimed = await conn.fetchval(
                """UPDATE website_content_briefs SET cms_status='sending',cms_last_error=NULL,
                          cms_connection_id=$3,updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND cms_status IN ('not_sent','failed')
                     AND article_status='approved' RETURNING id""",
                brief_id,workspace_id,connection_id,
            )
        if claimed is None:
            raise HTTPException(status_code=409, detail="wordpress_article_delivery_in_progress")
        delivery_claimed = True
        stable_slug = "oma-content-" + brief_id.hex
        existing = await _request(row["site_url"],row["username"],password,"GET","posts",
                                  params={"slug":stable_slug,"status":"draft","context":"edit"})
        if existing.status_code != 200:
            raise HTTPException(status_code=502, detail="wordpress_draft_lookup_failed")
        existing_items = existing.json()
        if not isinstance(existing_items,list):
            raise HTTPException(status_code=502, detail="wordpress_draft_lookup_invalid")
        if existing_items:
            data = existing_items[0]
            response_status_ok = isinstance(data,dict) and isinstance(data.get("id"),int)
        else:
            response = await _request(row["site_url"],row["username"],password,"POST","posts",json={
                "title": row["article_title"],
                "slug": stable_slug,
                "content": _html_from_markdown(row["article_body"]),
                "status": "draft",
                "excerpt": row["meta_description"],
            })
            response_status_ok = response.status_code in (200,201)
            data = response.json() if response_status_ok else {}
        if not response_status_ok:
            async with _pool(request).acquire() as conn:
                await conn.execute(
                    """UPDATE website_content_briefs SET cms_status='failed',
                              cms_last_error=$3,updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND cms_status='sending'""",
                    brief_id,workspace_id,"wordpress_http_" + str(response.status_code),
                )
            raise HTTPException(status_code=502, detail="wordpress_draft_creation_failed")
        data = response.json()
        if not isinstance(data,dict) or not isinstance(data.get("id"),int):
            raise HTTPException(status_code=502, detail="wordpress_post_response_invalid")
        post_url = _safe_post_link(row["site_url"], data.get("link"))
        async with _pool(request).acquire() as conn:
            await conn.execute(
                """UPDATE website_content_briefs SET cms_status='draft_created',
                          cms_post_id=$3,cms_post_url=$4,cms_synced_at=now(),updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND cms_status='sending'""",
                brief_id,workspace_id,data["id"],post_url,
            )
        delivery_claimed = False
        return {"sent_as_draft": True,"post_id":data["id"],"post_url":post_url,
                "status":"draft_created","notice":"WordPress post saved as draft only; it is not public."}
    except HTTPException:
        if delivery_claimed:
            try:
                async with _pool(request).acquire() as conn:
                    await conn.execute(
                        """UPDATE website_content_briefs SET cms_status='failed',
                                  cms_last_error='wordpress_draft_delivery_failed',updated_at=now()
                           WHERE id=$1 AND workspace_id=$2 AND cms_status='sending'""",
                        brief_id,workspace_id,
                    )
            except Exception:
                pass
        raise
    except Exception:
        try:
            async with _pool(request).acquire() as conn:
                await conn.execute(
                    """UPDATE website_content_briefs SET cms_status='failed',
                              cms_last_error='wordpress_delivery_unavailable',updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND cms_status='sending'""",
                    brief_id,workspace_id,
                )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="wordpress_draft_delivery_unavailable") from None


@router.post("/articles/{brief_id}/publish")
async def publish_wordpress_article(brief_id: UUID, payload: WordPressPublish, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    if payload.confirm_publish is not True:
        raise HTTPException(status_code=422, detail="explicit_publish_confirmation_required")
    publish_claimed = False
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """SELECT b.cms_post_id,b.cms_status,b.article_status,c.site_url,c.username,
                          c.encrypted_application_password,c.id AS connection_id
                   FROM website_content_briefs b
                   JOIN workspace_wordpress_connections c
                     ON c.id=b.cms_connection_id AND c.workspace_id=b.workspace_id
                   WHERE b.id=$1 AND b.workspace_id=$2 AND c.status='verified'""",
                brief_id,payload.workspace_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="wordpress_article_or_connection_not_found")
        if row["article_status"] != "approved":
            raise HTTPException(status_code=409, detail="article_editorial_approval_required")
        if row["cms_status"] != "draft_created" or not row["cms_post_id"]:
            raise HTTPException(status_code=409, detail="wordpress_draft_required_before_publish")
        password = _decrypt(row["encrypted_application_password"],payload.workspace_id,row["connection_id"])
        async with _pool(request).acquire() as conn:
            claimed = await conn.fetchval(
                """UPDATE website_content_briefs SET cms_status='publishing',updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND cms_status='draft_created'
                     AND article_status='approved' RETURNING id""",
                brief_id,payload.workspace_id,
            )
        if claimed is None:
            raise HTTPException(status_code=409, detail="wordpress_publish_in_progress")
        publish_claimed = True
        response = await _request(row["site_url"],row["username"],password,"POST",
                                  "posts/" + str(row["cms_post_id"]),json={"status":"publish"})
        if response.status_code not in (200,201):
            async with _pool(request).acquire() as conn:
                await conn.execute(
                    """UPDATE website_content_briefs SET cms_status='draft_created',updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND cms_status='publishing'""",
                    brief_id,payload.workspace_id,
                )
            raise HTTPException(status_code=502, detail="wordpress_publish_failed")
        data = response.json()
        if not isinstance(data,dict) or data.get("status") != "publish":
            async with _pool(request).acquire() as conn:
                await conn.execute(
                    """UPDATE website_content_briefs SET cms_status='draft_created',updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND cms_status='publishing'""",
                    brief_id,payload.workspace_id,
                )
            raise HTTPException(status_code=502, detail="wordpress_publish_unconfirmed")
        published_url = _safe_post_link(row["site_url"], data.get("link"))
        async with _pool(request).acquire() as conn:
            await conn.execute(
                """UPDATE website_content_briefs SET cms_status='published',
                          cms_post_url=$3,cms_synced_at=now(),updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND cms_status='publishing'""",
                brief_id,payload.workspace_id,published_url,
            )
        publish_claimed = False
        return {"published":True,"post_url":published_url,"status":"published"}
    except HTTPException:
        if publish_claimed:
            try:
                async with _pool(request).acquire() as conn:
                    await conn.execute(
                        """UPDATE website_content_briefs SET cms_status='draft_created',updated_at=now()
                           WHERE id=$1 AND workspace_id=$2 AND cms_status='publishing'""",
                        brief_id,payload.workspace_id,
                    )
            except Exception:
                pass
        raise
    except Exception:
        try:
            async with _pool(request).acquire() as conn:
                await conn.execute(
                    """UPDATE website_content_briefs SET cms_status='draft_created',updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND cms_status='publishing'""",
                    brief_id,payload.workspace_id,
                )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="wordpress_publish_unavailable") from None
