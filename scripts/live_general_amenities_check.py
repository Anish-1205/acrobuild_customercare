"""Exercise general amenity discovery with the real CS API and Sarvam."""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app import api
from services.amenity_search_service import live_amenity_index, projects_with_amenities


index = live_amenity_index()
expected = {entry["project"]["projectName"] for entry in index.values() if entry["amenities"]}
pools = {project["projectName"] for project in projects_with_amenities(index, ["Swimming Pool"])[0]}
assert expected and pools, "Live amenity catalogue unavailable"
results = []


def ask(client, endpoint, conversation_id, question):
    response = client.post(endpoint, json={"issue": question, "conversation_id": conversation_id})
    response.raise_for_status()
    payload = response.json() if not endpoint.endswith("stream") else next(
        event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done"
    )
    results.append({"endpoint": endpoint, "question": question, "answer": payload["answer"],
                    "pending": payload.get("pending_project_lookup"), "source_status": payload.get("source_status")})
    Path("logs/live_general_amenities_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    assert payload["source_status"] == "live_api", payload["answer"]
    return payload


with TestClient(api) as client:
    for endpoint in ("/api/support/assist", "/api/support/assist/stream"):
        conversation_id = "amenity-filter-live-" + str(uuid.uuid4())
        filtered = ask(client, endpoint, conversation_id, "swimming pool kontya projects madhe aahe?")
        assert {reply["value"] for reply in filtered["quick_replies"]} == pools
        details = ask(client, endpoint, conversation_id, "purna amenity list ani location sanga")
        assert set(details["pending_project_lookup"]["options"]) == pools, details["answer"]
        assert {reply["value"] for reply in details["quick_replies"]} == pools
        selected_name = sorted(pools)[0]
        selected = ask(client, endpoint, conversation_id, selected_name)
        assert selected_name in selected["answer"]
        assert "Swimming Pool" in selected["answer"]
        for question in ("konse projects me amenities hai?", "amenities kay tar projects madhe aahe?"):
            conversation_id = "amenity-live-" + str(uuid.uuid4())
            first = ask(client, endpoint, conversation_id, question)
            assert set(first["pending_project_lookup"]["options"]) == expected, first["answer"]
            pool = ask(client, endpoint, conversation_id, "mala swimming pool pahije")
            assert set(pool["pending_project_lookup"]["options"]) == pools, pool["answer"]
            selected_name = sorted(pools)[0]
            selected = ask(client, endpoint, conversation_id, selected_name)
            assert selected_name in selected["answer"], selected["answer"]
            assert "Swimming Pool" in selected["answer"], selected["answer"]
        conversation_id = "amenity-project-live-" + str(uuid.uuid4())
        ask(client, endpoint, conversation_id, "Vishwajeet Precious Phase-V ka price kya hai?")
        followup = ask(client, endpoint, conversation_id, "kya amenities hai ismein?")
        assert "Vishwajeet Precious Phase-V" in followup["answer"], followup["answer"]
        assert not followup.get("quick_replies"), followup["answer"]
print(f"PASS: {len(results)} live turns across both assist endpoints", flush=True)
