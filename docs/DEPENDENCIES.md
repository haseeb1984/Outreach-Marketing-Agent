# Dependency Map

- Backend: `backend/requirements.txt` (FastAPI, Uvicorn, Pydantic Settings, asyncpg, cryptography, DNS and pytest/httpx tooling).
- Frontend: `frontend/package.json` (Next.js 15, React 19, TypeScript).
- PostgreSQL and external provider credentials are runtime services/configuration, not package dependencies.
- Keep backend and frontend install/build workflows independent and validate environment parity across deployment targets.
