"""Validated environment-backed settings for the API."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Outreach Marketing Agent API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str | None = None
    secret_key: str | None = None
    # Must point to an operator-managed proxy that enforces destination IP policy at connection time.
    trusted_egress_proxy_url: str | None = None
    # Set to the real HTTPS origin in each deployment to enable canonical URLs/sitemap.
    public_base_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "Outreach Marketing Agent"
    smtp_starttls: bool = True
    # High-entropy shared secret for the provider-neutral inbound reply gateway.
    outreach_webhook_secret: str | None = None
    # Meta WhatsApp Cloud API credentials are staging/production secrets, never client-side.
    meta_whatsapp_access_token: str | None = None
    meta_whatsapp_app_secret: str | None = None
    meta_whatsapp_webhook_verify_token: str | None = None
    # Non-secret Meta asset identifiers; keep workspace-specific IDs in tenant storage for SaaS.
    meta_whatsapp_phone_number_id: str | None = None
    meta_whatsapp_waba_id: str | None = None


settings = Settings()
