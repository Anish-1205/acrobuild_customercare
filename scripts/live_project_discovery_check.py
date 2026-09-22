"""Live discovery/selection regression and uncached Phase-V amenity evidence."""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app import api
from services import acrobuild_company_service as cs
from services.conversation_store_service import (
    COOKIE_NAME, ConversationSession, build_pending_project_lookup_marker,
)


def main():
    projects = cs._request_json("/api/cs/projects")
    project = next(p for p in projects if p["projectName"] == "Vishwajeet Precious Phase-V")
    path = f"/api/cs/projects/{project['id']}/amenities"
    amenities = cs._request_json(path)
    results = {"checked_at": datetime.now(timezone.utc).isoformat(),
               "project": project, "amenities_endpoint": cs._company_scoped_path(path),
               "raw_amenities_response": amenities, "turns": []}
    baseline = "--baseline" in sys.argv
    output = Path("logs/project_discovery_baseline.json" if baseline else "docs/live_project_discovery_results.json")
    with TestClient(api) as client:
        for endpoint in ("/api/support/assist", "/api/support/assist/stream"):
            conversation_id = "discovery-live-" + str(uuid.uuid4())
            for question in ("mee kada em projects vunnayi?", project["projectName"],
                             "indhulo em em amenities vunnayi?"):
                response = client.post(endpoint, json={"issue": question, "conversation_id": conversation_id,
                                                      "prefer_fast_response": True, "limit": 2})
                response.raise_for_status()
                payload = response.json() if not endpoint.endswith("stream") else next(
                    event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")
                results["turns"].append({"endpoint": endpoint, "question": question, "response": payload})
                output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                print(question, "=>", payload["answer"], flush=True)
                if not baseline:
                    assert payload["source_status"] == "live_api"
                    if question.startswith("mee"):
                        assert payload["pending_project_lookup"]["purpose"] == "explore_project"
                        assert str(len(payload["quick_replies"])) in payload["answer"]
                    elif question == project["projectName"]:
                        assert not payload.get("pending_project_lookup"), payload["answer"]
                        assert project["projectName"] in payload["answer"]
                        assert any(c.get("project", {}).get("id") == project["id"] for c in payload["matched_chunks"])
                    else:
                        assert project["projectName"] in payload["answer"]
                        assert any(c.get("endpoint") == path and c.get("status") == "completed"
                                   for c in payload["data_api_calls"])
            if not baseline:
                # Recreate the previously stored generic discovery marker in
                # an isolated server-side conversation, with real API/LLM calls.
                conversation_id = "legacy-discovery-live-" + str(uuid.uuid4())
                state = {"kind": "selection", "entity": "project", "scope": {},
                         "original_issue": "What projects do you have with you?",
                         "options": [p["projectName"] for p in cs.customer_facing_projects(projects)]}
                session = ConversationSession(client.cookies.get(COOKIE_NAME), conversation_id)
                session.append("mee kada em projects vunnayi?", "Nenu ae project check cheyali?",
                               marker=build_pending_project_lookup_marker(state))
                response = client.post(endpoint, json={"issue": project["projectName"],
                                                      "conversation_id": conversation_id,
                                                      "prefer_fast_response": True, "limit": 2})
                response.raise_for_status()
                payload = response.json() if not endpoint.endswith("stream") else next(
                    event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")
                results["turns"].append({"endpoint": endpoint, "question": "Legacy selection: " + project["projectName"],
                                         "response": payload})
                output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                assert payload["source_status"] == "live_api"
                assert not payload.get("pending_project_lookup"), payload["answer"]
                assert project["projectName"] in payload["answer"]
                assert any(c.get("project", {}).get("id") == project["id"] for c in payload["matched_chunks"])
    print("Live raw amenities:", json.dumps(amenities), flush=True)
    print("PASS" if not baseline else "BASELINE CAPTURED", flush=True)


if __name__ == "__main__":
    main()
