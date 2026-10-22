"""FastAPI application entry point and crawlable public marketing surface.

Public marketing pages deliberately describe planned capabilities accurately. They do
not imply that billing, account management, or outreach integrations are already live.
"""
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import urljoin, urlsplit

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.core.config import settings
from app.services.secret_safe_logging import install_secret_redaction

# Install before importing route modules so accidental credential-bearing log records
# are sanitized before any configured handler formats them.
install_secret_redaction()

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
    application.state.subscription_store = None
    application.state.billing_lifecycle_store = None
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
        from app.services.subscription_store import SubscriptionStore
        from app.services.billing_lifecycle_store import BillingLifecycleStore
        application.state.prospect_store = ProspectStore(pool)
        application.state.campaign_store = CampaignStore(pool)
        application.state.delivery_store = DeliveryStore(pool)
        application.state.conversation_store = ConversationStore(pool)
        application.state.subscription_store = SubscriptionStore(pool)
        application.state.billing_lifecycle_store = BillingLifecycleStore(pool)
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


def _cors_origins() -> list[str]:
    """Normalize exact HTTPS frontend origins for credentialed browser requests."""
    configured = [item.strip() for item in (settings.frontend_origins or "").split(",") if item.strip()]
    if not configured and settings.public_base_url:
        configured = [settings.public_base_url.strip()]
    origins: list[str] = []
    for value in configured:
        try:
            parsed = urlsplit(value)
            if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
                continue
            if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                continue
            port = parsed.port
            origin = "https://" + parsed.hostname.lower() + (f":{port}" if port is not None and port != 443 else "")
            if origin not in origins:
                origins.append(origin)
        except ValueError:
            continue
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

from app.api.auth_routes import router as auth_router
from app.api.prospect_routes import router as prospect_router
from app.api.campaign_routes import router as campaign_router
from app.api.delivery_routes import router as delivery_router
from app.api.conversation_routes import router as conversation_router
from app.api.billing_routes import router as billing_router
from app.api.paddle_routes import router as paddle_router
from app.api.analytics_routes import router as analytics_router
from app.api.integration_routes import router as integration_router
from app.api.research_routes import router as research_router
from app.api.website_audit_routes import router as website_audit_router
from app.api.domain_routes import router as domain_router
from app.api.project_routes import router as project_router
from app.api.workspace_invitation_routes import router as invitation_router
from app.api.account_routes import router as account_router
from app.api.workspace_member_routes import router as workspace_member_router
from app.api.workspace_settings_routes import router as workspace_settings_router
from app.api.email_account_routes import router as email_account_router
from app.api.workspace_routes import router as workspace_router
from app.api.dashboard_routes import router as dashboard_router
from app.api.meta_whatsapp_webhook_routes import router as meta_whatsapp_webhook_router
from app.api.whatsapp_account_routes import router as whatsapp_account_router

app.include_router(auth_router)
app.include_router(prospect_router)
app.include_router(campaign_router)
app.include_router(delivery_router)
app.include_router(conversation_router)
app.include_router(billing_router)
app.include_router(paddle_router)
app.include_router(analytics_router)
app.include_router(integration_router)
app.include_router(research_router)
app.include_router(website_audit_router)
app.include_router(domain_router)
app.include_router(project_router)
app.include_router(invitation_router)
app.include_router(account_router)
app.include_router(workspace_member_router)
app.include_router(workspace_settings_router)
app.include_router(email_account_router)
app.include_router(workspace_router)
app.include_router(dashboard_router)
app.include_router(meta_whatsapp_webhook_router)
app.include_router(whatsapp_account_router)

PUBLIC_PAGES = [
    ("/", "Outreach Marketing Agent"),
    ("/product", "Product"),
    ("/pricing", "Pricing"),
    ("/faq", "Frequently asked questions"),
    ("/privacy", "Privacy policy"),
    ("/terms", "Terms of use"),
    ("/contact", "Contact and support"),
]


def _canonical(path: str) -> str | None:
    base = (settings.public_base_url or "").strip().rstrip("/") + "/"
    if not base.strip("/"):
        return None
    return urljoin(base, path.lstrip("/"))


def _page(title: str, description: str, path: str, body: str) -> HTMLResponse:
    canonical = _canonical(path)
    canonical_tag = (
        f'<link rel="canonical" href="{escape(canonical, quote=True)}">'
        if canonical
        else ""
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} | Outreach Marketing Agent</title>
<meta name="description" content="{escape(description, quote=True)}">
<meta name="robots" content="index,follow">
{canonical_tag}
<style>
:root{{color-scheme:light;--ink:#172033;--muted:#536176;--line:#dce3ed;--paper:#f6f8fb;--accent:#1749a5;--surface:#fff}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
a{{color:var(--accent);text-underline-offset:.2em}}a:focus-visible{{outline:3px solid #e0a400;outline-offset:3px}}
.skip{{position:absolute;left:-9999px;top:auto}}.skip:focus{{left:1rem;top:1rem;background:white;padding:.75rem;z-index:5}}
header,main,footer{{width:min(1080px,calc(100% - 2rem));margin-inline:auto}}
header{{display:flex;gap:1.5rem;align-items:center;justify-content:space-between;padding:1.2rem 0;border-bottom:1px solid var(--line)}}
nav{{display:flex;gap:1rem;flex-wrap:wrap}}nav a{{font-weight:600}}.brand{{font-weight:800;text-decoration:none;color:var(--ink)}}
main{{padding:3rem 0 4rem}}.hero{{padding:clamp(1.5rem,5vw,4rem);background:var(--surface);border:1px solid var(--line);border-radius:1.25rem}}
h1{{font-size:clamp(2rem,5vw,3.4rem);line-height:1.12;max-width:17ch;margin:.25rem 0 1rem}}h2{{line-height:1.25;margin-top:2rem}}p,li{{max-width:75ch}}.eyebrow{{color:var(--accent);font-weight:750;letter-spacing:.06em;text-transform:uppercase}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:1rem;margin-top:1.5rem}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:.9rem;padding:1.25rem}}.button{{display:inline-block;background:var(--accent);color:white;font-weight:700;text-decoration:none;padding:.75rem 1rem;border-radius:.55rem}}
.muted{{color:var(--muted)}}footer{{border-top:1px solid var(--line);padding:1.5rem 0 2.5rem}}@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{scroll-behavior:auto!important;animation:none!important;transition:none!important}}}}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to main content</a>
<header><a class="brand" href="/">Outreach Marketing Agent</a>
<nav aria-label="Main navigation"><a href="/product">Product</a><a href="/pricing">Pricing</a><a href="/faq">FAQ</a><a href="/app">Sign in</a><a href="/docs">API docs</a></nav></header>
<main id="main">{body}</main>
<footer><p><strong>Outreach Marketing Agent</strong></p>
<p class="muted">Evidence-led research and human-reviewed outreach. Planned features are not advertised as live integrations.</p>
<nav aria-label="Footer navigation"><a href="/product">Product</a><a href="/pricing">Pricing</a><a href="/faq">FAQ</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/contact">Contact</a><a href="/docs">API docs</a></nav></footer>
</body></html>"""
    return HTMLResponse(html)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Liveness endpoint; does not imply database readiness."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready", tags=["operations"])
async def readiness() -> Response:
    """Report readiness only when the configured PostgreSQL connection is usable."""
    from fastapi.responses import JSONResponse

    pool = getattr(app.state, "db_pool", None)
    if pool is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "database_not_configured"},
        )
    try:
        async with pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
            schema_ready = await connection.fetchval(
                """SELECT
                     to_regclass('public.workspace_domains') IS NOT NULL
                     AND to_regclass('public.domain_verification_challenges') IS NOT NULL
                     AND to_regclass('public.workspace_jobs') IS NOT NULL
                     AND to_regclass('public.app_users') IS NOT NULL
                     AND to_regclass('public.workspace_memberships') IS NOT NULL
                     AND to_regclass('public.auth_sessions') IS NOT NULL
                     AND to_regclass('public.security_audit_events') IS NOT NULL
                     AND to_regclass('public.auth_rate_limit_buckets') IS NOT NULL
                     AND to_regclass('public.crm_prospects') IS NOT NULL
                     AND to_regclass('public.outreach_campaigns') IS NOT NULL
                     AND to_regclass('public.outreach_drafts') IS NOT NULL
                     AND to_regclass('public.outreach_draft_events') IS NOT NULL
                     AND to_regclass('public.outreach_contact_controls') IS NOT NULL
                     AND to_regclass('public.outreach_deliveries') IS NOT NULL
                     AND to_regclass('public.outreach_conversation_messages') IS NOT NULL
                     AND to_regclass('public.workspace_subscriptions') IS NOT NULL
                     AND to_regclass('public.feature_usage_reservations') IS NOT NULL
                     AND to_regclass('public.billing_provider_events') IS NOT NULL
                     AND to_regclass('public.schema_migrations') IS NOT NULL
                     AND to_regclass('public.meta_whatsapp_webhook_events') IS NOT NULL
                     AND to_regclass('public.workspace_whatsapp_accounts') IS NOT NULL
                     AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='crm_prospects' AND column_name='contact_phone_e164')
                     AND (SELECT count(*) FROM schema_migrations
                          WHERE version IN (
                            '001_workspace_domain_verification.sql',
                            '002_workspace_jobs.sql',
                            '003_authentication_foundation.sql',
                            '004_auth_rate_limits.sql',
                            '005_session_csrf_tokens.sql',
                            '006_password_reset_tokens.sql',
                            '007_crm_prospects.sql',
                            '008_campaigns_and_approval_queue.sql',
                            '009_contact_controls.sql',
                            '010_outbound_delivery_queue.sql',
                            '011_conversation_webhook_inbox.sql',
                            '012_delivery_outcome_uncertainty.sql',
                            '013_subscription_entitlements_and_usage.sql',
                            '014_billing_provider_event_ledger.sql',
                            '020_meta_whatsapp_webhook_inbox.sql',
                            '021_workspace_whatsapp_accounts.sql',
                            '022_prospect_whatsapp_phone.sql'
                          )) = 17"""
            )
            if not schema_ready:
                return JSONResponse(
                    status_code=503,
                    content={"status": "not_ready", "reason": "database_schema_not_migrated"},
                )
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "database_unavailable"},
        )
    return JSONResponse(status_code=200, content={"status": "ready", "database": "ok"})


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> HTMLResponse:
    body = """
<section class="hero">
<p class="eyebrow">Research · relevance · responsible outreach</p>
<h1>Plan better partnerships with evidence, not guesswork.</h1>
<p>Outreach Marketing Agent is being built as a multi-project workspace for researching relevant public-facing prospects, preparing personalized outreach, reviewing replies, and measuring outcomes.</p>
<p><a class="button" href="/product">Explore the planned product</a></p>
<p class="muted">Account registration and the initial workspace foundation are available. Paid subscriptions, verified production billing, and live provider sending integrations are not yet available; do not treat the platform as fully launched.</p>
</section>
<section aria-labelledby="principles"><h2 id="principles">Built around trust and relevance</h2>
<div class="grid">
<article class="card"><h3>Evidence-backed research</h3><p>Prospect recommendations are intended to include source URLs, observation dates, fit reasons, and reviewable evidence.</p></article>
<article class="card"><h3>Human approval first</h3><p>Outreach drafts are designed for review before sending, with opt-out controls and provider limits.</p></article>
<article class="card"><h3>Customer data isolation</h3><p>The target SaaS architecture requires server-side authorization, workspace isolation, and verified subscription entitlements.</p></article>
</div></section>
<section><h2>Designed for real-world workflows</h2><p>Explore the <a href="/product">planned product capabilities</a>, read about the <a href="/pricing">pricing status</a>, or visit the <a href="/faq">frequently asked questions</a>. Features and integrations will be described as available only after implementation and verification.</p></section>
"""
    return _page(
        "Evidence-led outreach and partnership research",
        "Discover the planned Outreach Marketing Agent platform for evidence-backed prospect research, human-reviewed outreach, and campaign insights.",
        "/",
        body,
    )


@app.get("/product", response_class=HTMLResponse, include_in_schema=False)
def product_page() -> HTMLResponse:
    body = """
<section class="hero"><p class="eyebrow">Product overview</p><h1>A workspace for research-to-outreach workflows</h1>
<p>The intended product brings product research, public prospect discovery, CRM workflows, message drafting, approval, reply management, and campaign reporting into one secure SaaS workspace.</p></section>
<section><h2>Planned capabilities</h2><div class="grid">
<article class="card"><h3>Product discovery</h3><p>Analyze a website and, where authorized, a repository to assemble source-backed product facts and campaign angles.</p></article>
<article class="card"><h3>Prospect research</h3><p>Discover relevant public-facing prospects, retain source evidence, explain fit, and deduplicate records.</p></article>
<article class="card"><h3>CRM and campaigns</h3><p>Organize workspaces, projects, prospect stages, campaign membership, and approved drafts.</p></article>
<article class="card"><h3>Messaging integrations</h3><p>Planned provider adapters for eligible email and official WhatsApp Business workflows, subject to provider requirements.</p></article>
<article class="card"><h3>Paid SaaS plans</h3><p>Planned subscriptions with server-verified entitlements, usage limits, billing lifecycle handling, and secure hosted checkout.</p></article>
<article class="card"><h3>Responsible marketing</h3><p>Planned evidence-based content planning, AI crawler discoverability, approval-controlled publishing, and measured growth analytics.</p></article>
</div></section>
<p><strong>Availability notice:</strong> Account and workspace foundations exist, but this is not a full production SaaS launch. Research-provider coverage, production billing, live email/WhatsApp sending, analytics integrations, and the complete end-to-end customer workflow must be verified before being described as generally available.</p>
"""
    return _page(
        "Product overview",
        "Planned features for prospect research, CRM, human-reviewed outreach, paid SaaS workflows, and responsible AI discoverability.",
        "/product",
        body,
    )


@app.get("/pricing", response_class=HTMLResponse, include_in_schema=False)
def pricing_page() -> HTMLResponse:
    body = """
<section class="hero"><p class="eyebrow">Pricing status</p><h1>Subscription plans are not open for purchase yet</h1>
<p>The platform's billing and entitlement system is planned but not yet available. No plan, payment method, recurring charge, or quota is being offered on this page today.</p></section>
<section><h2>What pricing will explain before launch</h2><ul>
<li>Included features and workspace/team limits.</li><li>AI and prospect research quotas and any fair-use limits.</li>
<li>Connected account and outreach limits where applicable.</li><li>Billing period, supported currency, renewal, cancellation, failed-payment and refund terms.</li>
</ul><p>Real prices and checkout will be published only after the payment provider, merchant eligibility, launch countries, and subscription lifecycle have been verified.</p></section>
"""
    return _page(
        "Pricing and subscription status",
        "Current pricing status for Outreach Marketing Agent. Paid subscriptions and checkout are not yet available.",
        "/pricing",
        body,
    )


@app.get("/faq", response_class=HTMLResponse, include_in_schema=False)
def faq_page() -> HTMLResponse:
    body = """
<section class="hero"><p class="eyebrow">FAQ</p><h1>Frequently asked questions</h1>
<h2>Can I create an account or buy a subscription now?</h2><p>Account registration and the initial workspace foundation are available. Paid subscriptions, production checkout, and live paid entitlements are not yet available and must pass release checks before launch.</p>
<h2>Will the AI send outreach automatically?</h2><p>The initial design uses human-reviewed drafts. Any future sending automation must be explicitly enabled, compliant with provider rules, rate-limited, auditable, and stopped by opt-out or safety controls.</p>
<h2>Can AI search agents discover the website?</h2><p>The site is being prepared for crawlable public content, sitemap and robots rules, and a maintained llms.txt directory. These help communicate the site's public content but cannot guarantee that any crawler will visit, index, cite, or recommend it.</p>
<h2>Will the platform store payment card details?</h2><p>The intended billing design uses a provider-hosted checkout or approved tokenization and does not store raw card numbers or CVV in this application.</p>
<h2>Are all listed features available?</h2><p>No. Features described as planned are not live features. Availability will be updated only after implementation and verification.</p>
</section>
"""
    return _page(
        "Frequently asked questions",
        "Answers about availability, subscriptions, responsible outreach, AI crawler discovery, and data security.",
        "/faq",
        body,
    )



@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
def privacy_page() -> HTMLResponse:
    body = """
<section class="hero"><p class="eyebrow">Privacy notice</p><h1>How workspace and outreach data is handled</h1>
<p>This notice describes the intended handling of information in the current development version. It is not a substitute for a final jurisdiction-specific privacy notice; the service must publish its operator identity, applicable legal basis, contact details and final retention schedule before paid launch.</p></section>
<section><h2>Information processed</h2><ul>
<li>Account information such as email address, authentication/session records and security events.</li>
<li>Workspace, project, team invitation, campaign, prospect and draft records entered or generated by users.</li>
<li>Public-source URLs and research evidence, website audit results, message delivery metadata and replies when those features are used.</li>
<li>Provider credentials supplied by an administrator. Supported provider secrets are designed to be encrypted at rest and are not returned in account-list responses.</li>
<li>Operational metadata needed to prevent abuse, enforce workspace access and investigate service errors.</li>
</ul><h2>Purposes and sharing</h2><p>Data is processed to provide the requested workspace features, secure accounts, enforce plan and usage rules, deliver user-approved communications, and maintain the service. Connected providers receive only the data needed for a user-requested operation. Public prospect sources should be used responsibly; the service must not be used to collect private data or bypass access controls. The service does not intentionally sell personal information.</p>
<h2>Retention, security and user choices</h2><p>Records may be retained while a workspace is active and for a limited period needed for security, dispute resolution, backups or legal obligations. A precise retention schedule and deletion workflow remain launch requirements. Use the account export and deletion controls where available, and disable connected accounts when no longer needed. Never place passwords, access tokens or private keys in campaign content or support messages.</p>
<h2>Contact</h2><p>See the <a href="/contact">contact and support page</a>. A verified public privacy contact must be configured by the service operator before general availability.</p></section>
"""
    return _page("Privacy notice", "Privacy information for accounts, workspaces, prospect research and provider integrations.", "/privacy", body)


@app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def terms_page() -> HTMLResponse:
    body = """
<section class="hero"><p class="eyebrow">Terms of use</p><h1>Use the service responsibly</h1>
<p>The product is under active development. These preliminary terms explain basic use expectations; they are not final legal terms and must be reviewed for the operator's jurisdiction before commercial launch.</p></section>
<section><h2>Account and workspace responsibility</h2><p>Keep credentials secure, provide accurate account information, and ensure that people invited to a workspace are authorized. You are responsible for activity performed through your account and for safeguarding connected-provider credentials.</p>
<h2>Research and outreach compliance</h2><p>Use prospect research only for lawful, relevant business purposes. Respect privacy rights, marketing and anti-spam laws, provider policies, contact preferences and opt-outs. Do not use the service to send unsolicited bulk messages, impersonate others, scrape private data, evade rate limits, or bypass technical access controls. You must have a valid basis and any required consent or opt-in before contacting a person through a channel that requires it.</p>
<h2>AI and evidence limitations</h2><p>AI-generated research and drafts may be incomplete or wrong. Review source evidence, recipient identity, claims, links and message content before approval. A source URL or automated check is not a guarantee of accuracy, deliverability, search ranking or business results.</p>
<h2>Availability and billing</h2><p>Features marked as planned or pending are not offered as live capabilities. Paid checkout and paid entitlements remain unavailable until the service publishes verified plans and final billing, cancellation, renewal and refund terms. Nothing on this site creates a promise of uninterrupted availability or a guaranteed marketing outcome.</p>
<h2>Changes and contact</h2><p>Final terms, governing law, limitation of liability, termination and dispute procedures must be published before general availability. See <a href="/contact">contact and support</a> for current support-routing status.</p></section>
"""
    return _page("Terms of use", "Preliminary terms for responsible use of Outreach Marketing Agent during development.", "/terms", body)


@app.get("/contact", response_class=HTMLResponse, include_in_schema=False)
def contact_page() -> HTMLResponse:
    body = """
<section class="hero"><p class="eyebrow">Contact and support</p><h1>Get help with your workspace</h1>
<p>The public support contact has not yet been configured for general availability. Existing customers should use the support channel supplied during onboarding or in their service agreement.</p></section>
<section><h2>Security and privacy requests</h2><p>Do not send passwords, session cookies, SMTP passwords, Meta access tokens, API keys or payment details in a support request. Include only the workspace identifier and a concise description of the issue when appropriate.</p>
<h2>Before commercial launch</h2><p>The service operator must publish a monitored support address, a privacy-request contact, expected response times and an escalation route before accepting paid subscriptions.</p><p><a href="/privacy">Privacy notice</a> · <a href="/terms">Terms of use</a></p></section>
"""
    return _page("Contact and support", "Current support contact status and safe guidance for service requests.", "/contact", body)


@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
def llms_txt() -> PlainTextResponse:
    content = """# Outreach Marketing Agent

> Planned multi-tenant SaaS for evidence-backed prospect research and human-reviewed outreach. planned features are not live until implemented and verified; the full platform is still in development.

## Public pages
- [Home](/): Product purpose and current development status.
- [Product](/product): Planned capabilities and availability notice.
- [Pricing](/pricing): Current billing availability; subscriptions are not open yet.
- [FAQ](/faq): Answers about product status, security, and AI crawler discoverability.
- [Privacy](/privacy): Data processing and security overview.
- [Terms](/terms): Preliminary responsible-use terms.
- [Contact](/contact): Current support contact status.
- [API documentation](/docs): Current FastAPI API documentation.

## Product principles
- Research evidence should include public source URLs and observation dates.
- Human approval is the default for outreach.
- Respect opt-outs, provider rules, rate limits, and customer privacy.
- Never claim a planned feature is live without verification.

## Important
This file is a discovery aid, not an API contract, authorization mechanism, or guarantee that AI systems will index or cite the website.
"""
    return PlainTextResponse(content, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots_txt() -> PlainTextResponse:
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/",
        "Disallow: /account",
        "Disallow: /dashboard",
        "Disallow: /billing",
        "Disallow: /workspaces",
        "Disallow: /projects",
    ]
    if settings.public_base_url:
        lines.append(f"Sitemap: {settings.public_base_url.rstrip('/')}/sitemap.xml")
    return PlainTextResponse("\n".join(lines) + "\n")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml() -> Response:
    base = (settings.public_base_url or "").strip().rstrip("/")
    if not base:
        return PlainTextResponse(
            "PUBLIC_BASE_URL must be configured to publish an absolute canonical sitemap.\n",
            status_code=503,
        )
    urls = []
    for path, _ in PUBLIC_PAGES:
        location = escape(urljoin(base + "/", path.lstrip("/")))
        urls.append(f"<url><loc>{location}</loc></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls)
        + "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/api-info", include_in_schema=False)
def api_info() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running", "docs": "/docs"}
