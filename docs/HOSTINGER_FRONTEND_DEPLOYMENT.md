# Hostinger frontend deployment

The customer-facing frontend must run on **Hostinger Business**, not Vercel. The FastAPI backend remains on Vercel at `https://outreach-marketing-agent.vercel.app`.

## Agreed architecture
- **Hostinger Business:** Next.js + TypeScript customer-facing website, pricing, FAQ, account entry pages, and dashboard.
- **Vercel:** existing FastAPI backend/API only.
- **Database:** server-side access only; frontend must never connect directly.
- **Billing:** Paddle hosted checkout and signed webhook handled by backend.
- **Transport:** HTTPS from frontend to backend; no secrets in browser code.

## Deployment steps
1. Create a Hostinger Node.js application in hPanel using a supported Node.js runtime.
2. Upload the `frontend/` directory via the Hostinger ZIP/manual workflow.
3. Set build command `npm install && npm run build` and start command `npm start`; set the app root to `frontend` or upload its contents as the application root.
4. Set `NEXT_PUBLIC_API_BASE_URL=https://outreach-marketing-agent.vercel.app` in Hostinger's environment settings, then build/restart.
5. Configure the production frontend origin in backend CORS and authentication origin validation. Verify credentials, CSRF, and session-cookie behavior before login/registration acceptance.
6. Smoke-test public pages, responsive layout, registration, email verification, login/logout, dashboard data and Paddle sandbox checkout/webhook. Real billing remains disabled until all tests pass.

## Important release gates
- The production Hostinger domain/subdomain and account credentials are not recorded in this repo, so this document does not claim a deployment was performed.
- Login/registration calls are not end-to-end ready until the backend explicitly allows the Hostinger frontend origin and cross-origin session handling is tested.
- Terms and privacy pages require actual operator/legal details and review before launch.
- Do not put API keys, Paddle secrets, database credentials or provider tokens in `NEXT_PUBLIC_*` variables.
