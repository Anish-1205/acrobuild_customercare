"""Real application requests: no mocked model, API, or conversation storage."""
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app import api

scenarios = {
    "precious": ["vishwajeet lo amenities em em vunnai?", "Vishwajeet Precious"],
    "cost": ["What is the cost in Vishwajeet?", "Vishwajeet Precious"],
    "location": ["Where is the project located?", "Vishwajeet Precious"],
    "wing": ["Show me wings in Vishwajeet Myspace", "Venus A", "1", "__first_flat__"],
}
results = {}
with TestClient(api) as client:
    for name, questions in scenarios.items():
        turns = []
        results[name] = turns
        conversation_id = "live-audit-" + str(uuid.uuid4())
        for question in questions:
            if question == "__first_flat__":
                question = turns[-1]["response"]["pending_project_lookup"]["options"][0]
            print("USER:", question, flush=True)
            response = client.post("/api/support/assist/stream", json={"issue": question, "conversation_id": conversation_id})
            response.raise_for_status()
            events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
            payload = next(event["response"] for event in events if event.get("type") == "done")
            turns.append({"user": question, "response": payload})
            print("ASSISTANT:", payload.get("answer"), flush=True)
            Path("docs/live_disambiguation_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

for name, turns in results.items():
    assert all(t["response"].get("source_status") == "live_api" for t in turns), name
    assert all("could not verify one live answer" not in t["response"]["answer"] for t in turns), name
assert results["precious"][1]["response"]["answer"].count("\n- ") == 14
assert any(c.get("endpoint") == "/api/cs/projects/52/amenities" and c.get("status") == "completed"
           for c in results["precious"][1]["response"]["data_api_calls"])
assert "base pricing" in results["cost"][1]["response"]["answer"]
assert "Venus A" in results["wing"][1]["response"]["answer"]
assert "flat" in results["wing"][2]["response"]["answer"].lower()
assert "Flat " + results["wing"][3]["user"] in results["wing"][3]["response"]["answer"]
print("ALL LIVE CONVERSATION ASSERTIONS PASSED", flush=True)
