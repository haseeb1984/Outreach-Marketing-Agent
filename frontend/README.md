# Hostinger frontend

This customer-facing Next.js app is intended for **Hostinger Business, not Vercel**. The FastAPI backend remains on Vercel at `https://outreach-marketing-agent.vercel.app`.

## Local build
- Node.js 20 or 22
- `npm install`
- Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_BASE_URL`
- `npm run build`
- `npm start`

## Hostinger deployment
1. Create a Node.js application in Hostinger hPanel using a supported Node runtime.
2. Upload this folder's source files using the agreed ZIP/manual workflow, or connect the repository if that deployment mode is available on the plan.
3. Build command: `npm install && npm run build`; start command: `npm start`.
4. Set `NEXT_PUBLIC_API_BASE_URL` in Hostinger environment settings and build/restart.
5. Configure the actual frontend origin in backend CORS and auth origin validation. Session cookie behavior must be tested; use a custom API subdomain under the same site when available rather than relying on third-party cookies.
6. Smoke-test public pages, responsive layout, registration, login/logout, email verification and dashboard API calls. Keep live Paddle checkout disabled until sandbox acceptance passes.

The terms/privacy pages, account flows, API origin configuration and full dashboard are not yet production accepted. Never put API keys, Paddle secrets, database credentials or provider tokens in frontend code or `NEXT_PUBLIC_*` variables.
