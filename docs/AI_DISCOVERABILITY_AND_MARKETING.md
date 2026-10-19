# AI Discoverability and Self-Marketing Requirements

This document defines how the public product website can be discovered by search engines and AI-powered search/research agents, and how the product may market itself responsibly. These are requirements, not a claim that crawler discovery or marketing automation is already implemented. Crawlers cannot be forced to index or recommend a site.

## 1. Public crawlable product surface
- Maintain fast, server-rendered or statically rendered public pages for the home page, product capabilities, use cases, integrations that are actually available, pricing, documentation, FAQs, changelog/release notes, contact/support, and legal policies.
- Each page must have original, useful, current content, descriptive title/description, one clear main heading, canonical URL, language metadata, crawlable internal links, and correct HTTP status.
- Provide XML sitemap(s) containing only canonical, public, indexable URLs; update last-modified metadata only when content materially changes.
- Provide a standards-compliant robots.txt that references the sitemap and sets the intended crawl policy. Do not treat robots.txt as access control.
- Publish /llms.txt as a concise, maintained directory for language-model tools to understand the product and find authoritative public documentation. It supplements normal web standards; do not assume every AI crawler consumes it.
- Where appropriate, expose clean machine-readable public documentation (for example OpenAPI for the public API only) and JSON-LD structured data only when it accurately represents visible page content.
- Use meaningful HTML rather than relying exclusively on client-side rendering for important public content. Avoid cloaking: crawlers and people should receive materially equivalent public information.
- Never put private customer content, private reports, tokens, lead data, unpublished campaigns, or authenticated application routes in public sitemaps, llms.txt, structured data, or marketing content.
- Keep authenticated data protected by authentication and authorization. Noindex is a crawl hint, not a security boundary.

## 2. AI and search crawler policy
- Maintain a reviewed list of known crawler user agents and their documented policies, but do not assume user-agent strings are authentic; apply normal abuse controls.
- Choose explicitly whether each recognized crawler may access public marketing pages. Public pages may be allowed; private/account/API endpoints remain protected regardless of crawler identity.
- Do not block all bots indiscriminately if discovery is a product goal, but do block abusive traffic, exploit attempts, excessive request rates, and private-path probing.
- Honor applicable published crawler controls and provider terms. Do not bypass bot challenges, access controls, robots policies, or paywalls on third-party websites during prospect research.
- Rate-limit and cache crawler requests; serve predictable status codes; avoid infinite URL/calendar/filter spaces and duplicate-content traps.
- Monitor aggregate crawl errors and server load without logging unnecessary personal data. Do not claim that any AI provider has indexed or recommended the site unless there is verifiable evidence.

## 3. Responsible self-marketing engine
- Add an optional marketing workspace that proposes a content and distribution plan based on verified product capabilities, public search demand, customer questions, and observed product analytics.
- Content workflow: collect evidence → generate draft → validate claims/links → accessibility/SEO checks → human review and approval → publish/schedule → measure outcomes → update or retire stale content.
- Content types may include useful tutorials, use-case pages, feature documentation, comparison pages with fair evidence, release notes, FAQs, templates, and original research based on consented/legitimate data.
- Every factual product claim must be tied to a verified feature or source. Do not publish roadmap items as launched features, fabricated testimonials, fake ratings, invented statistics, or misleading competitor claims.
- Require human approval for initial publishing. Any later auto-publishing must be an explicit workspace opt-in, use approved templates and topic boundaries, enforce rate limits, keep audit/version history, support rollback, and stop on policy/quality failures.
- Never generate doorway pages, keyword-stuffed pages, mass near-duplicate pages, hidden text, cloaking, fake backlinks, or other manipulative search-engine content.
- Outreach promotion must be relevant, compliant, provider-authorized and subject to suppression/opt-out, sending limits, identity transparency, and human approval by default. No unsolicited bulk spam or automated posting/comments where prohibited.
- Social publishing, email newsletters, partner directories and other external channels must use official APIs or permitted workflows; verify authorization and platform rules before implementing an integration.
- AI-generated content must be fact-checked, useful to real readers, edited for accuracy, and maintained. The objective is discovery and genuine usefulness, not content volume alone.

## 4. Growth analytics and feedback loop
- Track aggregate impressions, organic landing-page visits, referral sources, qualified signups, activation, paid conversion, retention, and content performance where lawful and privacy-respecting.
- Define attribution assumptions and avoid claiming a campaign caused revenue without adequate evidence.
- Use Search Console and other official webmaster tools where the owner authorizes connection; do not scrape private analytics accounts.
- Identify content gaps and recommend improvements; do not automatically rewrite critical pricing, legal, privacy, or security statements.
- Provide an admin review queue, evidence/source links, generated draft preview, SEO/accessibility checks, scheduled status, publishing history, and rollback.
- Offer kill switches and per-channel budgets; no marketing automation may override product security, customer consent, unsubscribe/suppression, or provider restrictions.

## 5. Acceptance tests
- Public home, product, pricing, docs and policy pages return intended status codes, canonical metadata, accessible semantic content and working internal links.
- Sitemap validates and includes only intended canonical public pages; robots.txt and /llms.txt are reachable and contain no private data.
- Authenticated pages and APIs cannot be read anonymously, by a crawler, or by another tenant; verify with automated authorization tests.
- Structured data matches visible content and validates without invented claims.
- Crawl simulation confirms no unbounded URL generation, redirect loops, sensitive query-string indexing, or excessive request rates.
- Marketing draft cannot publish without the required approval/opt-in; unverified claims and unsafe content are blocked or sent for review.
- Opt-out, kill switch, channel quotas and audit trail are tested before any outreach/publishing automation is enabled.

## 6. Release truthfulness
This capability improves crawlability and provides a controlled marketing workflow; it cannot guarantee search rankings, AI citations, crawler visits, sales, or virality. Report only measured outcomes.
