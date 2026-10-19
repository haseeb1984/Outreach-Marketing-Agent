# Safety, Privacy and Outreach Compliance

This is an engineering policy, not legal advice. Review applicable privacy, marketing, messaging and platform rules before launch.

## Mandatory controls
- Draft-and-approve is the default. Sending remains disabled until a provider is configured and the user explicitly approves the campaign.
- Do not scrape private accounts, bypass logins/CAPTCHAs, evade platform limits, or bypass restrictions.
- Use permitted public sources and retain a source URL, observation date, fit score and reason for every prospect.
- Do not infer or store sensitive personal traits for targeting; collect only information relevant to professional contact.
- Honor opt-outs promptly. Maintain suppression lists and check them before every send and follow-up.
- Stop follow-ups after opt-out, refusal, bounce, complaint or manual pause.
- Enforce provider/account quotas, rate limits, quiet hours, deduplication and a campaign kill switch.
- Never misrepresent the sender, invent a prior relationship, fabricate product capabilities, or generate deceptive testimonials.
- Use the official WhatsApp Business Platform/Cloud API and respect its eligibility, opt-in, template and messaging requirements.
- Use OAuth/provider-approved authentication. Encrypt tokens at rest, support revocation and never log secrets.
- Provide appropriate export, deletion and retention controls.

## Human approval and automation gates
1. Research output must be evidence-linked and reviewable.
2. Drafts are editable and labeled as suggestions.
3. Initial release requires human approval before sending.
4. Any later automation is explicit opt-in, scoped, rate-limited and auditable.
5. A failed eligibility or safety check blocks sending.

## SSRF protections for website analysis
- Accept HTTP/HTTPS only.
- Resolve DNS and reject loopback, private, link-local, multicast, reserved and cloud metadata IP ranges for IPv4 and IPv6.
- Re-check every redirect; limit redirects, response size and timeout.
- Never forward internal cookies, auth headers or credentials to user-supplied destinations.
- Block unsupported ports and non-web protocols; do not trust hostname strings without resolution.
- Test redirects and DNS-rebinding scenarios where feasible.

## Release blockers
Critical/high authorization bypass, secret exposure, SSRF to internal services, duplicate-send races, suppression bypass or cross-tenant data leakage blocks release until fixed and retested.
