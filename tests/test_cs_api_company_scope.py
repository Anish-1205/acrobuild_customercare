import io
import json

import pytest

from services import acrobuild_company_service as cs


@pytest.mark.parametrize("path,expected", [
    ("/api/cs/company", "/api/cs/16/company"),
    ("/api/cs/projects", "/api/cs/16/projects"),
    ("/api/cs/projects/51/amenities", "/api/cs/16/projects/51/amenities"),
    ("/api/cs/projects/51/wings", "/api/cs/16/projects/51/wings"),
    ("/api/cs/projects/51/typologies", "/api/cs/16/projects/51/typologies"),
    ("/api/cs/wings/7/typologies", "/api/cs/16/wings/7/typologies"),
    ("/api/cs/wings/7/inventory", "/api/cs/16/wings/7/inventory"),
])
def test_cs_paths_include_configured_company(monkeypatch, path, expected):
    monkeypatch.setattr(cs, "CS_API_COMPANY_ID", "16")
    assert cs._company_scoped_path(path) == expected


def test_request_uses_company_path_query_and_api_key(monkeypatch):
    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen["url"] = request.full_url
            seen["api_key"] = request.get_header("Apikey")
            return io.BytesIO(json.dumps([]).encode())

    monkeypatch.setattr(cs, "CS_API_COMPANY_ID", "16")
    monkeypatch.setattr(cs, "CS_API_BASE_URL", "https://example.test")
    monkeypatch.setattr(cs, "CS_API_KEY", "test-key")
    monkeypatch.setattr(cs.urllib.request, "build_opener", lambda *args: Opener())

    assert cs._request_json("/api/cs/wings/7/inventory", {"availableOnly": "true"}) == []
    assert seen == {
        "url": "https://example.test/api/cs/16/wings/7/inventory?availableOnly=true",
        "api_key": "test-key",
    }


def test_snapshot_is_rejected_for_another_company(monkeypatch):
    monkeypatch.setattr(cs, "CS_API_COMPANY_ID", "22")
    assert cs._load_snapshot_fallback("/api/cs/projects") is None


def test_company_id_is_required(monkeypatch):
    monkeypatch.setattr(cs, "CS_API_COMPANY_ID", "")
    assert not cs.is_cs_api_configured()
    with pytest.raises(RuntimeError, match="ACROBUILD_CS_API_COMPANY_ID"):
        cs._company_scoped_path("/api/cs/projects")
