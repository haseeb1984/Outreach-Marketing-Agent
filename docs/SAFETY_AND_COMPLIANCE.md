# Safety, Privacy and Outreach Compliance

This document defines product guardrails, not legal advice. Launching in a market requires review of applicable privacy, marketing, messaging and platform rules.

## Mandatory controls
- Draft-and-approve is the default. Sending must remain disabled until the user configures a provider and explicitly approves the campaign.
- Do not scrape private accounts, bypass logins, evade CAPTCHAs, rotate identities to avoid limits, or bypass platform restrictions.
- Discover prospects from permitted public sources and record a source URL, observation date, fit score, and reason for inclusion.
- Do not infer or store sensitive personal traits for targeting. Collect only information relevant to a legitimate professional context.
- Honor opt-outs promptly. Maintain project/global suppression lists and check them before every send and follow-up.
- Stop automated follow-ups after an opt-out, clear refusal, bounce, complaint, or manual pause.
- Enforce per-provider and per-account quotas, rate limits, quiet hours, deduplication and a campaign kill switch.
- Do not misrepresent the sender, fabricate product capabilities, invent a prior relationship, or generate deceptive reviews/testimonials.
- Use the official WhatsApp Business Platform/Cloud API and respect its opt-in, template, conversation-window and quality requirements.
- Use OAuth or provider-approved authentication. Encrypt tokens at rest, support revocation, rotate keys, and never log secrets.
- Provide data export/deletion and retention controls appropriate to the release.

## Human approval and automation gates
1. Research output is reviewable and evidence-linked.
2. Drafts are editable and clearly labeled as AI-assisted suggestions.
3. A human explicitly approves a message/campaign before sending in the initial release.
4. Later automation is opt-in, scoped, rate-limited and auditable; it cannot override suppression, provider policy, or account limits.
5. Any critical safety or eligibility check failure blocks the send.

## Web-fetch and SSRF requirements
- Accept only HTTP/HTTPS URLs.
- Resolve DNS and reject loopback, private, link-local, multicast, reserved and cloud metadata IP ranges for both IPv4 and IPv6.
- Re-check every redirect target; limit redirects, response size and timeout.
- Do not forward internal cookies, authorization headers or credentials to user-supplied destinations.
- Block unsupported ports and non-web protocols; do not trust a hostname string without resolving it.
- Tests must cover DNS rebinding/redirect scenarios where feasible.

## Security release blockers
Critical/high authorization bypass, secret exposure, SSRF to internal services, duplicate-send race, suppression bypass, or cross-tenant data leakage blocks release until fixed and retested.
