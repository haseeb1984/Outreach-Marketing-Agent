# Hostinger deployment runbook

## Hosting split
- Frontend: Next.js app on Hostinger Business Node.js hosting.
- Backend: FastAPI at the configured HTTPS BACKEND_API_ORIGIN (currently documented as https://outreach-marketing-agent.vercel.app).
- Do not deploy the frontend to Vercel. Never place database credentials, SMTP passwords, Paddle secrets, Meta tokens, signing keys, or cookies in frontend environment variables.

## Build the upload bundle
Preferred: download the outreach-marketing-agent-hostinger artifact from a successful Hostinger Frontend CI run. The ZIP must contain package.json, .env.example, next.config.ts, and app/ at its root. Current CI is not green, so an old artifact is not proof of the latest source.
Alternative from a Windows checkout: run frontend/scripts/package-hostinger.ps1 from the repository root. This creates a source ZIP, not a prebuilt deployment. Verify the output file exists and inspect the archive before uploading.

## Hostinger configuration
1. Create a Node.js application using a Node runtime supported by the Hostinger plan.
2. Extract the ZIP into the application root.
3. Install dependencies and build from that root: npm install --no-audit --no-fund, then npm run build.
4. Configure server-side BACKEND_API_ORIGIN to the real HTTPS backend origin.
5. Configure NEXT_PUBLIC_SITE_URL to the final HTTPS frontend origin and, if staffed, NEXT_PUBLIC_SUPPORT_EMAIL to a public support inbox. Rebuild after changing NEXT_PUBLIC_* values.
6. Start with npm start using Hostinger Node.js application settings.
The frontend requires a Node.js runtime for Next.js server rendering and its same-origin API proxy. Static-only hosting is not interchangeable with this bundle.

## Backend configuration and safety
- Set the exact Hostinger HTTPS origin in backend FRONTEND_ORIGINS.
- Configure database connection, migrations, secure session/signing keys, email delivery and provider settings in backend environment only.
- Never commit real .env files or include them in ZIPs. Do not expose secrets via NEXT_PUBLIC_*, browser code, logs, URLs, or error messages.
- Keep real payments and outbound provider sending disabled until sandbox/acceptance checks are complete.

## Release acceptance checklist
- [ ] Current frontend type-check and production build pass.
- [ ] Current backend CI and PostgreSQL migration/integration tests pass.
- [ ] Upload ZIP is from the same green commit and contains no real .env, build output, dependencies, or credentials.
- [ ] HTTPS works and session/CSRF cookies are host-only and secure.
- [ ] Registration, verification, login, password reset, session rotation, logout and recovery are verified on the real domain.
- [ ] Workspace isolation and role authorization are checked with two separate workspaces/users.
- [ ] SMTP delivery, official Meta WhatsApp staging, signed Paddle webhooks and subscription entitlements are acceptance-tested before enabling live traffic.
- [ ] Database backup/restore, monitoring, accessibility, performance and SEO checks are evidenced.

Do not call the product production-ready until all release-critical checks above have evidence. A code commit or green build alone does not prove live provider or production-domain acceptance.
