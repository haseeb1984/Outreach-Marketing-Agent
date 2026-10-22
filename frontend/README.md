# Hostinger frontend

This customer-facing Next.js app is intended for **Hostinger Business, not Vercel**. The FastAPI backend remains on Vercel at `https://outreach-marketing-agent.vercel.app` unless the deployment configuration is changed.

## Configuration and secrets policy

- Keep deployment-specific configuration in the application's `.env` / Hostinger Node.js environment settings; use `.env.example` only as a safe template.
- Never commit a real `.env`, production credential, token, API key, Paddle secret, webhook secret, or database password.
- The only browser-visible setting currently required is `NEXT_PUBLIC_API_BASE_URL`. It is an API origin, not a credential. Next.js embeds `NEXT_PUBLIC_*` values into browser assets at build time, so change it and rebuild when the origin changes.
- Paddle private credentials, webhook verification secrets, email-provider credentials, database configuration and other secrets belong only in the backend environment, never in frontend `.env` values or browser code.
- Do not put secrets in URLs, logs, screenshots, generated ZIPs, or source files.

## Local build

- Node.js 20 or 22
- `npm install`
- Copy `.env.example` to `.env.local`; change `NEXT_PUBLIC_API_BASE_URL` only if the backend origin differs.
- `npm run build`
- `npm start`

## Hostinger deployment

1. Create a Node.js application in Hostinger hPanel using a supported Node runtime.
2. Upload the frontend source files using the final ZIP/manual workflow.
3. Build command: `npm install && npm run build`; start command: `npm start`.
4. Configure `NEXT_PUBLIC_API_BASE_URL` through the Hostinger application's environment settings (or the `.env` mechanism supported by the selected Node.js app), then rebuild/restart.
5. Configure the actual frontend origin in the backend's `FRONTEND_ORIGINS` environment variable for CORS and auth origin validation. Do not leave example domains in production.
6. Smoke-test public pages, responsive layout, registration, login/logout, email verification and dashboard API calls. Keep live Paddle checkout disabled until sandbox acceptance passes.

The terms/privacy pages, account flows, API origin configuration and full dashboard are not yet production accepted. The final ZIP must contain `.env.example` only, not a real `.env` or credentials. Do not claim deployment or production acceptance until the relevant checks have passed.
