# Hostinger frontend

The customer-facing Next.js app is deployed on **Hostinger Business**. The FastAPI backend remains on Vercel at `https://outreach-marketing-agent.vercel.app`.

## Same-origin API and session handling

- The frontend proxies `/api/*` server-side to `BACKEND_API_ORIGIN`. Browser requests use same-origin paths, so the session and CSRF cookies are scoped to the Hostinger site rather than depending on third-party cookies.
- Configure `BACKEND_API_ORIGIN` in Hostinger's server-side environment settings. It is an origin, not a secret.
- Configure the exact HTTPS Hostinger frontend origin in backend `FRONTEND_ORIGINS`. The backend must also have its real `PUBLIC_BASE_URL`, database, email and security settings configured.
- If the backend sets secure `__Host-` cookies, the production frontend must be HTTPS. Do not test production cookie behavior on plain HTTP.
- Do not set browser-visible API secrets. No credential belongs in a `NEXT_PUBLIC_*` variable.

## Secrets policy

- Use `.env.example` as a safe template; never commit or include a real `.env` in the ZIP.
- Paddle private credentials, webhook secrets, SMTP passwords, database URLs, Meta tokens and signing keys belong only in the backend environment.
- Never put credentials, cookies, verification tokens or provider exception bodies into logs, URLs, screenshots or ZIPs.

## Local build

- Node.js 20 or 22
- `npm install`
- Set `BACKEND_API_ORIGIN` in local server environment if the default is not correct.
- `npm run build`
- `npm start`

## Hostinger manual deployment

1. Create a Node.js application in Hostinger hPanel using a supported Node runtime.
2. Upload the final frontend ZIP and install dependencies.
3. Build with `npm install && npm run build`; start with `npm start`.
4. Set `BACKEND_API_ORIGIN` in the Hostinger server-side environment, then rebuild/restart.
5. Set the exact frontend HTTPS origin in backend `FRONTEND_ORIGINS`; never leave example domains in production.
6. Verify registration, email verification, login, session refresh, CSRF-protected actions, logout, workspace isolation and the dashboard against the actual production domains.
7. Keep paid checkout disabled until Paddle sandbox checkout, signed webhook handling and subscription lifecycle are verified.

This configuration removes the frontend's dependency on cross-site browser cookies, but production acceptance still requires deployment-origin testing. The final ZIP must contain `.env.example` only, never a real `.env` or credentials.
