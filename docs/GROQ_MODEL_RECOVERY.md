# Groq model discovery and automatic recovery

The AI outreach provider is Groq Cloud. The OpenAI-compatible request format is used only for protocol compatibility; requests are sent to the configured Groq API origin.

## Model selection

- Read Groq's official Supported Models page and its **Production Models** section.
- Intersect those documented production model IDs with the authenticated Groq `/openai/v1/models` response. A model is eligible only when both sources agree it is production-listed and active for the configured account.
- Prefer the configured `AI_MODEL` when it remains eligible; otherwise select the first eligible production model in Groq's published order.
- Cache the discovered production list for five minutes per running backend process.

## Automatic recovery

If Groq rejects a selected model with a model-not-found, deprecated/decommissioned, or unsupported-model response, refresh the official catalog and retry with another eligible production model. Remember the last successful model for the lifetime of that backend process.

Do not switch models for authentication errors, account/billing errors, rate limits, exhausted quotas, network failures, or malformed model output. Those failures need credential, account, quota, or service remediation; silently switching models would not fix them.

The active model is selected dynamically at runtime. The backend does **not** rewrite Vercel environment variables or commit model IDs during a customer request. This avoids giving a runtime request permission to mutate deployment configuration. The next request re-discovers the current official list after cache expiry, and a cold start independently selects a valid production model.

## Operator configuration

- `AI_API_KEY`: Groq API key (server-side secret)
- `AI_BASE_URL`: `https://api.groq.com/openai/v1`
- `AI_MODEL`: preferred Groq production model; automatic discovery replaces it at runtime if it is no longer eligible

Official references:
- https://console.groq.com/docs/models
- https://console.groq.com/docs/deprecations
- https://console.groq.com/docs/api-reference
