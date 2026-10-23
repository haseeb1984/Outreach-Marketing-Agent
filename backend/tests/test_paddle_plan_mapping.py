import pytest

from app.api.paddle_routes import _resolve_subscription_plan


PLANS = {
    "starter": {"price_id": "pri_starter", "entitlements": {"email": {"enabled": True}}},
    "growth": {"price_id": "pri_growth", "entitlements": {"email": {"enabled": True}}},
}


def test_resolves_plan_only_when_provider_price_and_custom_metadata_match():
    slug, plan = _resolve_subscription_plan({"workspace_id": "workspace-1", "plan_id": "starter"}, {"pri_starter"}, PLANS)
    assert slug == "starter"
    assert plan is PLANS["starter"]


def test_rejects_mismatched_plan_metadata_even_if_price_is_known():
    with pytest.raises(ValueError, match="subscription_plan_metadata_mismatch"):
        _resolve_subscription_plan({"plan_id": "growth"}, {"pri_starter"}, PLANS)


def test_rejects_missing_custom_metadata():
    with pytest.raises(ValueError, match="workspace_mapping_missing"):
        _resolve_subscription_plan(None, {"pri_starter"}, PLANS)


def test_rejects_missing_declared_plan():
    with pytest.raises(ValueError, match="subscription_plan_metadata_missing"):
        _resolve_subscription_plan({"workspace_id": "workspace-1"}, {"pri_starter"}, PLANS)


def test_rejects_unknown_provider_price():
    with pytest.raises(ValueError, match="subscription_plan_mapping_invalid"):
        _resolve_subscription_plan({"plan_id": "starter"}, {"pri_unknown"}, PLANS)


def test_rejects_ambiguous_price_mapping():
    plans = {"starter": {"price_id": "pri_same"}, "growth": {"price_id": "pri_same"}}
    with pytest.raises(ValueError, match="subscription_plan_mapping_invalid"):
        _resolve_subscription_plan({"plan_id": "starter"}, {"pri_same"}, plans)

from fastapi import HTTPException

from app.api import paddle_routes
from app.core.config import settings


def test_bootstrap_catalog_rejects_duplicate_price_ids(monkeypatch):
    monkeypatch.setattr(settings, "paddle_plans_json", '{"starter":{"price_id":"pri_same","entitlements":{}},"growth":{"price_id":"pri_same","entitlements":{}}}')
    with pytest.raises(HTTPException) as exc:
        paddle_routes._plans()
    assert exc.value.detail == "billing_plan_catalog_invalid"


def test_bootstrap_catalog_rejects_invalid_slug(monkeypatch):
    monkeypatch.setattr(settings, "paddle_plans_json", '{"Starter Plan":{"price_id":"pri_starter","entitlements":{}}}')
    with pytest.raises(HTTPException) as exc:
        paddle_routes._plans()
    assert exc.value.detail == "billing_plan_catalog_invalid"
