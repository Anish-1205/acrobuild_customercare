from services.rag_evaluation_service import evaluate_rag_response


def test_online_metrics_use_retrieved_context():
    result = evaluate_rag_response(
        "What is the project location?",
        {
            "answer": "The project location is Hyderabad.",
            "matched_chunks": [{
                "title": "Project location",
                "record_body": "The project location is Hyderabad.",
                "score": 8.0,
            }],
            "retrieval_mode": "lexical",
            "source_status": "workspace",
        },
        [],
    )

    assert result["metrics"]["context_precision"]["score"] == 1.0
    assert result["metrics"]["groundedness"]["score"] > 0
    assert result["metrics"]["context_recall"]["status"] == "not_available"
    assert result["metrics"]["mrr"]["score"] is None


def test_live_api_hit_rate_tracks_failed_calls():
    result = evaluate_rag_response(
        "Show projects",
        {"answer": "Nine projects are available.", "matched_chunks": []},
        [
            {"status": "completed"},
            {"status": "failed"},
        ],
    )

    assert result["metrics"]["retrieval_hit_rate"]["score"] == 0.5
    assert result["evidence"]["successful_data_api_call_count"] == 1
    assert result["metrics"]["groundedness"]["status"] == "not_available"


def test_hallucination_risk_treats_lower_as_better():
    result = evaluate_rag_response(
        "project location",
        {
            "answer": "project location",
            "matched_chunks": [{"record_body": "project location", "score": 8}],
        },
        [],
    )

    assert result["metrics"]["hallucination_risk"]["score"] == 0.0
    assert result["metrics"]["hallucination_risk"]["status"] == "good"