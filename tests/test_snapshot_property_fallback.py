from api_context import _enforce_live_property_data
from services import acrobuild_company_service as company_service


def _call(provider, status, endpoint):
    return {"provider": provider, "status": status, "endpoint": endpoint,
            "cache_hit": provider.endswith("snapshot"), "response_summary": {"kind": "list"}}


def test_snapshot_fallback_keeps_project_answer_and_discloses_date():
    endpoint = "/api/cs/projects"
    payload = {"route": "property", "answer": "Which project should I check? - Vishwajeet Paradise",
               "quick_replies": [{"label": "Vishwajeet Paradise", "value": "Vishwajeet Paradise"}]}
    calls = [_call("Acrobuild CS API", "failed", endpoint),
             _call("Acrobuild CS API snapshot", "cached", endpoint)]
    result = _enforce_live_property_data(payload, "Which project?", calls)
    assert result["source_status"] == "snapshot"
    assert "Live property data is unavailable" in result["answer"]
    assert "8 September 2026" in result["answer"]
    assert "Vishwajeet Paradise" in result["answer"]
    assert result["quick_replies"] == payload["quick_replies"]


def test_a_later_live_retry_of_the_same_endpoint_overrides_an_earlier_failure():
    # A single turn can call the same resource more than once (e.g. project
    # scope is resolved more than once during one turn); a live success on a
    # later attempt must not still be reported as "using saved data" just
    # because an earlier attempt at the exact same endpoint timed out first.
    endpoint = "/api/cs/projects"
    payload = {"route": "property", "answer": "Which wing should I check in Vishwajeet Precious Phase-V?"}
    calls = [
        _call("Acrobuild CS API", "failed", endpoint),
        _call("Acrobuild CS API snapshot", "cached", endpoint),
        _call("Acrobuild CS API", "completed", "/api/cs/projects/52/wings"),
        _call("Acrobuild CS API", "completed", endpoint),  # retry succeeds live
        _call("Acrobuild CS API", "completed", "/api/cs/projects/89/wings"),
    ]
    result = _enforce_live_property_data(payload, "which wing should I check?", calls)
    assert result["source_status"] == "live_api"
    assert "Live property data is unavailable" not in result["answer"]


def test_a_later_live_failure_of_the_same_endpoint_overrides_an_earlier_success():
    # The reverse must also hold: if the LAST attempt at a resource is the
    # one that failed, that failure is authoritative even though an earlier
    # attempt at the same endpoint happened to succeed.
    endpoint = "/api/cs/projects"
    payload = {"route": "property", "answer": "Which project should I check?"}
    calls = [
        _call("Acrobuild CS API", "completed", endpoint),
        _call("Acrobuild CS API", "failed", endpoint),
        _call("Acrobuild CS API snapshot", "cached", endpoint),
    ]
    result = _enforce_live_property_data(payload, "Which project?", calls)
    assert result["source_status"] == "snapshot"


def test_missing_snapshot_endpoint_does_not_claim_missing_amenities():
    payload = {"route": "property", "answer": "This project has no amenities."}
    calls = [_call("Acrobuild CS API snapshot", "cached", "/api/cs/projects"),
             _call("Acrobuild CS API", "failed", "/api/cs/projects/51/amenities")]
    result = _enforce_live_property_data(payload, "What amenities?", calls)
    assert result["source_status"] == "failed"
    assert "no amenities" not in result["answer"]


def test_cs_api_failure_reads_september_snapshot(monkeypatch):
    monkeypatch.setattr(company_service, "CS_API_COMPANY_ID", "16")
    monkeypatch.setattr(company_service, "CS_API_LIVE_ONLY", False)
    monkeypatch.setattr(company_service, "CS_API_CACHE_TTL_SECONDS", 0)
    monkeypatch.setattr(company_service, "_request_json", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    projects = company_service.get_company_projects()
    assert len(projects) == 9
    assert any(project.get("projectName") == "Vishwajeet Paradise" for project in projects)
