import json

from app.api import billing_routes
from app.api.billing_routes import PaddleCheckoutInput, _public_paddle_plans


def test_dashboard_checkout_plan_id_is_accepted():
    request = PaddleCheckoutInput(workspace_id="workspace-1", plan_id="pri_starter")
    assert request.plan_id == "pri_starter"
    assert request.price_id is None


def test_dashboard_checkout_accepts_legacy_price_id():
    request = PaddleCheckoutInput(workspace_id="workspace-1", price_id="pri_starter")
    assert request.price_id == "pri_starter"


def test_public_plan_contract_never_exposes_entitlements_or_secrets(monkeypatch):
    monkeypatch.setattr(billing_routes.settings, "paddle_api_key", "secret")
    monkeypatch.setattr(billing_routes.settings, "paddle_environment", "sandbox")
    monkeypatch.setattr(billing_routes.settings, "paddle_live_checkout_enabled", False)
    plans = {
        "pri_starter": {
            "slug": "starter",
            "name": "Starter",
            "description": "For small teams",
            "display_price": "19",
            "currency": "USD",
            "billing_interval": "month",
            "entitlements": {"email_sends": {"enabled": True, "monthly_limit": 100}},
            "api_key": "never-return-this",
        }
    }
    public = _public_paddle_plans(plans)
    assert public == [{
        "id": "pri_starter",
        "name": "Starter",
        "description": "For small teams",
        "display_price": "19",
        "currency": "USD",
        "billing_interval": "month",
        "checkout_available": True,
    }]
    assert "entitlements" not in json.dumps(public)
    assert "never-return-this" not in json.dumps(public)


def test_live_plan_is_not_checkout_available_until_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(billing_routes.settings, "paddle_api_key", "secret")
    monkeypatch.setattr(billing_routes.settings, "paddle_environment", "live")
    monkeypatch.setattr(billing_routes.settings, "paddle_live_checkout_enabled", False)
    public = _public_paddle_plans({"pri_starter": {"slug": "starter", "entitlements": {}}})
    assert public[0]["checkout_available"] is False
