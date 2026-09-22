"""Real CS API/LLM acceptance for project context and compound home types."""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from fastapi.testclient import TestClient
from services import acrobuild_company_service as cs


def main():
    projects = cs._request_json("/api/cs/projects")
    project = next(p for p in projects if p["projectName"] == "Vishwajeet Empire NX")
    typologies = cs._request_json(f"/api/cs/projects/{project['id']}/typologies")
    three_bhk_projects = [
        p["projectName"] for p in projects
        if any("3bhk" in str(t.get("typologyName") or t.get("typologyType") or "").lower().replace(" ", "")
               for t in cs._request_json(f"/api/cs/projects/{p['id']}/typologies"))
    ]
    results = {"project": project["projectName"], "typologies": typologies,
               "three_bhk_projects": three_bhk_projects, "turns": []}
    output = Path("docs/live_project_home_type_results.json")
    with TestClient(api) as client:
        for endpoint in ("/api/support/assist", "/api/support/assist/stream"):
            for questions in (
                ["What is the pricing in Vishwajeet Empire NX?", "2bhk matrame cheppu"],
                ["Tell me about Vishwajeet Empire NX", "indhulo 2bk and 3bhk details cheppu", "3bhk levva?"],
                ["Show 3BHK details", "Vishwajeet Empire NX"],
                ["what projects do you have?", "__select_nx__", "is there a 3bhk in this project?", "2bhk?"],
            ):
                conversation_id = "home-type-live-" + str(uuid.uuid4())
                for index, question in enumerate(questions):
                    if question == "__select_nx__":
                        question = project["projectName"]
                    response = client.post(endpoint, json={"issue": question, "conversation_id": conversation_id,
                                                          "prefer_fast_response": True, "limit": 2})
                    response.raise_for_status()
                    payload = response.json() if not endpoint.endswith("stream") else next(
                        e["response"] for e in map(json.loads, response.text.splitlines()) if e["type"] == "done")
                    results["turns"].append({"endpoint": endpoint, "question": question, "response": payload})
                    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(question, "=>", payload["answer"], flush=True)
                    assert payload["source_status"] == "live_api", payload["answer"]
                    if index:
                        assert project["projectName"] in payload["answer"]
                        assert not payload.get("pending_project_lookup"), payload["answer"]
                        if "2b" in question.lower():
                            assert "2BHK" in payload["answer"]
                        if "3b" in question.lower():
                            assert "3BHK" in payload["answer"]
                        if "and 3bhk" in question:
                            assert "3BHK" in payload["answer"]
                        assert {o.get("action") for o in payload.get("quick_replies", [])} == {"ticket", "site_visit", "call"}
            conversation_id = "home-type-filter-live-" + str(uuid.uuid4())
            response = client.post(endpoint, json={"issue": "what properties have 3bhk?",
                                                   "conversation_id": conversation_id,
                                                   "prefer_fast_response": True, "limit": 2})
            response.raise_for_status()
            payload = response.json() if not endpoint.endswith("stream") else next(
                e["response"] for e in map(json.loads, response.text.splitlines()) if e["type"] == "done")
            results["turns"].append({"endpoint": endpoint, "question": "what properties have 3bhk?",
                                     "response": payload})
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            assert [option["value"] for option in payload.get("quick_replies", [])] == three_bhk_projects
            assert "could not verify one live answer" not in payload["answer"].lower()
            if three_bhk_projects:
                response = client.post(endpoint, json={"issue": three_bhk_projects[0],
                                                       "conversation_id": conversation_id,
                                                       "prefer_fast_response": True, "limit": 2})
                response.raise_for_status()
                selected = response.json() if not endpoint.endswith("stream") else next(
                    e["response"] for e in map(json.loads, response.text.splitlines()) if e["type"] == "done")
                results["turns"].append({"endpoint": endpoint, "question": three_bhk_projects[0],
                                         "response": selected})
                output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                assert "3BHK:" in selected["answer"]
                assert three_bhk_projects[0] in selected["answer"]
                assert not selected.get("pending_project_lookup")
                assert "could not verify one live answer" not in selected["answer"].lower()
    print("ALL LIVE HOME-TYPE ASSERTIONS PASSED", flush=True)


if __name__ == "__main__":
    main()
