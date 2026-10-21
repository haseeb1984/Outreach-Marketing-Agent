"""FastAPI application entry point and crawlable public marketing surface.

Public marketing pages deliberately describe planned capabilities accurately. They do
not imply that billing, account management, or outreach integrations are already live.
"""
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import urljoin

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.core.config import settings

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create an optional PostgreSQL pool without running migrations at startup."""
    application.state.db_pool = None
    application.state.domain_authorization_store = None
    application.state.auth_store = None
    application.state.auth_rate_limiter = None
    application.state.prospect_store = None
    application.state.campaign_store = None
    application.state.delivery_store = None
    application.state.conversation_store = None
    if settings.database_url:
        pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=5,
            timeout=5,
            command_timeout=15,
        )
        from app.services.domain_authorization_store import DomainAuthorizationStore

        application.state.db_pool = pool
        application.state.domain_authorization_store = DomainAuthorizationStore(pool)
        from app.services.auth_store import AuthStore
        from app.services.auth_rate_limiter import AuthRateLimiter

        application.state.auth_store = AuthStore(pool)
        from app.services.prospect_store import ProspectStore
        from app.services.campaign_store import CampaignStore
        from app.services.delivery_store import DeliveryStore
        from app.services.conversation_store import ConversationStore
        application.state.prospect_store = ProspectStore(pool)
        application.state.campaign_store = CampaignStore(pool)
        application.state.delivery_store = DeliveryStore(pool)
        application.state.conversation_store = ConversationStore(pool)
        if settings.secret_key and len(settings.secret_key.encode('utf-8')) >= 32:
            application.state.auth_rate_limiter = AuthRateLimiter(pool, secret_key=settings.secret_key)
    try:
        yield
    finally:
        pool = getattr(application.state, "db_pool", None)
        if pool is not None:
            await pool.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Evidence-led, human-approved influencer and outreach campaign workspace.",
    lifespan=lifespan,
)

from app.api.auth_routes import router as auth_router
from app.api.prospect_routes import router as prospect_router
from app.api.campaign_routes import router as campaign_router
from app.api.delivery_routes import router as delivery_router
from app.api.conversation_routes import router as conversation_router

app.include_router(auth_router)
app.include_router(prospect_router)
app.include_router(campaign_router)
app.include_router(delivery_router)
app.include_router(conversation_router)
