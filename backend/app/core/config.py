"""Validated environment-backed settings for the API."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Outreach Marketing Agent API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str | None = None
    secret_key: str | None = None
    trusted_egress_proxy_url: str | None = None
    public_base_url: str | None = None
    frontend_origins: str = ""
    frontend_public_url: str | None = None
    brave_search_api_key: str | None = None
    provider_credential_encryption_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "Outreach Marketing Agent"
    smtp_starttls: bool = True
    # Comma-separated exact emails permitted to administer the entire SaaS. Empty disables this surface.
    platform_admin_emails: str = ""
    paddle_api_key: str | None = None
    paddle_webhook_secret: str | None = None
    paddle_environment: str = "sandbox"
    paddle_live_checkout_enabled: bool = False
    paddle_plans_json: str | None = None
    outreach_webhook_secret: str | None = None
    meta_whatsapp_access_token: str | None = None
    meta_whatsapp_app_secret: str | None = None
    meta_whatsapp_webhook_verify_token: str | None = None
    meta_whatsapp_phone_number_id: str | None = None
    meta_whatsapp_waba_id: str | None = None
    meta_graph_api_version: str | None = None


settings = Settings()
