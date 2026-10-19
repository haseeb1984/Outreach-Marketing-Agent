import asyncio

from app.services import persisted_website_growth_pipeline as pipeline


def test_persisted_pipeline_loads_domain_records_from_store(monkeypatch):
    class Store:
        async def get_verified_domains(self, *, workspace_id):
            assert workspace_id == "workspace-trusted"
            return [{
                "workspace_id": workspace_id,
                "domain": "client.example",
                "status": "verified",
                "revoked_at": None,
            }]

    captured = {}

    async def fake_pipeline(start_url, **kwargs):
        captured["start_url"] = start_url
        captured.update(kwargs)
        return {"status": "report_ready_for_human_review"}

    monkeypatch.setattr(pipeline, "discover_and_build_growth_report", fake_pipeline)
    result = asyncio.run(pipeline.discover_persisted_workspace_site(
        "https://client.example/",
        workspace_id="workspace-trusted",
        domain_store=Store(),
        business_type="retail",
        target_market="UK",
        target_queries=["running shoes"],
    ))
    assert result["status"] == "report_ready_for_human_review"
    assert captured["workspace_id"] == "workspace-trusted"
    assert captured["verified_domains"][0]["domain"] == "client.example"
