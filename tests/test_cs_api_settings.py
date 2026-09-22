import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.cs_api_settings import router, require_admin_user
from services import cs_api_settings_service as settings
from services import acrobuild_company_service as company
from services.internal_api_log_service import begin_data_api_trace, end_data_api_trace


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "settings.db")
    monkeypatch.setattr(company, "CS_API_BASE_URL", "https://original.example")
    monkeypatch.setattr(company, "CS_API_KEY", "original-secret")
    monkeypatch.setattr(company, "CS_API_COMPANY_ID", "1")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_user] = lambda: {"role": "admin"}
    return TestClient(app)


def test_save_persists_and_never_returns_key(client):
    assert client.get("/api/admin/cs-api-settings").json() == {
        "base_url": "https://original.example", "company_id": "1", "api_key_configured": True}
    result = client.put("/api/admin/cs-api-settings", json={
        "base_url": "http://new.example:9091/", "company_id": 23, "api_key": "replacement-secret"})
    assert result.status_code == 200
    assert "replacement-secret" not in result.text
    assert result.json()["base_url"] == "http://new.example:9091"
    assert company._cs_api_config()["api_key"] == "replacement-secret"
    assert company._company_scoped_path("/api/cs/projects") == "/api/cs/23/projects"
    result = client.put("/api/admin/cs-api-settings", json={
        "base_url": "http://new.example:9091", "company_id": 24, "api_key": ""})
    assert result.status_code == 200
    assert company._cs_api_config()["api_key"] == "replacement-secret"
    assert client.get("/api/admin/cs-api-settings").json()["company_id"] == "24"


@pytest.mark.parametrize("change", [
    {"base_url": "file:///etc/passwd"}, {"base_url": "https://user:pass@example.com"},
    {"base_url": "https://example.com?secret=value"}, {"base_url": "http://example.com:bad"},
    {"company_id": 0}, {"company_id": 1.5}, {"api_key": "bad\r\nheader"},
])
def test_rejects_invalid_settings(client, change):
    data = {"base_url": "https://example.com", "company_id": 3, "api_key": ""}
    data.update(change)
    assert client.put("/api/admin/cs-api-settings", json=data).status_code == 422
    assert company._cs_api_config()["company_id"] == "1"


def test_admin_authorization(client):
    client.app.dependency_overrides.clear()
    from api_context import require_workspace_user
    for role in ["owner", "agent"]:
        client.app.dependency_overrides[require_workspace_user] = lambda: {"role": role}
        assert client.get("/api/admin/cs-api-settings").status_code == 403
        assert client.put("/api/admin/cs-api-settings", json={
            "base_url": "https://example.com", "company_id": 3}).status_code == 403
    client.app.dependency_overrides.clear()
    assert client.get("/api/admin/cs-api-settings").status_code == 401


def test_runtime_requests_and_caches_switch_configuration(client, monkeypatch):
    monkeypatch.setattr(company, "CS_API_LIVE_ONLY", False)
    monkeypatch.setattr(company, "_CACHE", {})
    calls = []
    def request(path, params=None):
        config = company._cs_api_config()
        calls.append(config)
        return [{"id": config["company_id"]}]
    monkeypatch.setattr(company, "_request_json", request)
    token = begin_data_api_trace()
    try:
        assert company.get_company_projects() == [{"id": "1"}]
        settings.save_cs_api_settings("https://new.example", "new-key", 2, company._cs_api_defaults())
        assert company.get_company_projects() == [{"id": "2"}]
        assert company.get_company_projects() == [{"id": "2"}]
        assert len(calls) == 2
        assert calls[-1]["api_key"] == "new-key"
        assert company._load_snapshot_fallback("/api/cs/projects") is None
    finally:
        end_data_api_trace(token)
