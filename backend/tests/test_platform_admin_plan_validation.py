import pytest
from pydantic import ValidationError

from app.api.platform_admin_routes import PlanInput


def valid_payload(**overrides):
    payload = {
        "slug": "starter",
        "name": "Starter",
        "description": "Entry plan",
        "price_id": "pri_123abc",
        "display_price": "19.00",
        "currency": "USD",
        "billing_interval": "month",
        "entitlements": {"prospect_search": {"enabled": True, "monthly_limit": 100}},
        "active": True,
    }
    payload.update(overrides)
    return payload


def test_plan_input_accepts_valid_plan_and_entitlements():
    plan = PlanInput(**valid_payload())
    assert plan.slug == "starter"
    assert plan.entitlements["prospect_search"]["monthly_limit"] == 100


@pytest.mark.parametrize("slug", ["Starter", "../starter", "", "x" * 81])
def test_plan_input_rejects_invalid_slug(slug):
    with pytest.raises(ValidationError):
        PlanInput(**valid_payload(slug=slug))


@pytest.mark.parametrize("price_id", ["", "price_123", "pri_", "pri_ bad"])
def test_plan_input_rejects_invalid_paddle_price_id(price_id):
    with pytest.raises(ValidationError):
        PlanInput(**valid_payload(price_id=price_id))


@pytest.mark.parametrize("limit", [-1, True, 1.5, "100"])
def test_plan_input_rejects_non_integer_or_negative_limits(limit):
    with pytest.raises(ValidationError):
        PlanInput(**valid_payload(entitlements={"prospect_search": {"enabled": True, "monthly_limit": limit}}))


def test_plan_input_rejects_missing_enabled_boolean():
    with pytest.raises(ValidationError):
        PlanInput(**valid_payload(entitlements={"prospect_search": {"monthly_limit": 10}}))


def test_plan_input_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        PlanInput(**valid_payload(internal_secret="must-not-be-accepted"))


def test_plan_input_rejects_non_finite_json_numbers():
    with pytest.raises(ValidationError):
        PlanInput(**valid_payload(entitlements={"prospect_search": {"enabled": True, "threshold": float("nan")}}))
