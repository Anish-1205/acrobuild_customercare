import math
import re

# -----------------------------------
# ONLINE RAG EVALUATION
# -----------------------------------

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could",
    "do", "for", "from", "had", "has", "have", "how", "i", "in", "is",
    "it", "me", "my", "of", "on", "or", "please", "show", "that", "the",
    "there", "this", "to", "was", "what", "when", "where", "which", "who",
    "with", "would", "you", "your",
}


def _tokens(value):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _clamp(value):
    return round(max(0.0, min(float(value), 1.0)), 4)


def _metric(score, explanation, lower_is_better=False):
    if score is None:
        return {
            "score": None,
            "percent": None,
            "status": "not_available",
            "explanation": explanation,
        }
    normalized_score = _clamp(score)
    quality_score = 1.0 - normalized_score if lower_is_better else normalized_score
    status = "good" if quality_score >= 0.7 else "review" if quality_score >= 0.45 else "poor"
    return {
        "score": normalized_score,
        "percent": round(normalized_score * 100, 1),
        "status": status,
        "explanation": explanation,
    }


def _chunk_text(chunk):
    return " ".join(
        str(chunk.get(field, "") or "")
        for field in ("title", "excerpt", "body_text", "record_body")
    ).strip()


def evaluate_rag_response(issue, response_payload, data_api_calls=None):
    """Calculate transparent online proxy metrics for one chat answer.

    These metrics do not claim dataset-level recall, MRR, or NDCG because those
    require labelled expected documents. Missing evidence is returned as
    not_available rather than converted into a misleading numeric score.
    """
    response_payload = response_payload or {}
    data_api_calls = data_api_calls or []
    from services.answer_evidence_service import enrich_answer_evidence
    enrich_answer_evidence(response_payload, data_api_calls)
    answer = str(response_payload.get("answer", "") or "")
    matched_chunks = [
        chunk for chunk in response_payload.get("matched_chunks", [])
        if isinstance(chunk, dict)
    ]
    query_tokens = _tokens(issue)
    answer_tokens = _tokens(answer)
    chunk_token_sets = [_tokens(_chunk_text(chunk)) for chunk in matched_chunks]
    context_tokens = set().union(*chunk_token_sets) if chunk_token_sets else set()

    relevant_chunks = 0
    for chunk, chunk_tokens in zip(matched_chunks, chunk_token_sets):
        lexical_overlap = len(query_tokens.intersection(chunk_tokens))
        score = float(chunk.get("score", 0) or 0)
        if lexical_overlap > 0 or score >= 3.0:
            relevant_chunks += 1

    context_precision = (
        relevant_chunks / len(matched_chunks)
        if matched_chunks
        else None
    )
    answer_relevance = (
        len(query_tokens.intersection(answer_tokens))
        / math.sqrt(len(query_tokens) * len(answer_tokens))
        if query_tokens and answer_tokens
        else None
    )
    groundedness = (
        len(answer_tokens.intersection(context_tokens)) / len(answer_tokens)
        if answer_tokens and context_tokens
        else None
    )

    completed_calls = sum(
        1 for call in data_api_calls
        if str(call.get("status", "")).lower() in {"completed", "cached"}
    )
    retrieval_hit_rate = (
        completed_calls / len(data_api_calls)
        if data_api_calls
        else 1.0 if matched_chunks else 0.0
    )

    available_scores = [
        score for score in (context_precision, answer_relevance, groundedness, retrieval_hit_rate)
        if score is not None
    ]
    overall_score = sum(available_scores) / len(available_scores) if available_scores else None
    hallucination_risk = 1.0 - groundedness if groundedness is not None else None

    return {
        "version": "online-proxy-v1",
        "evaluation_type": "online_proxy",
        "retrieval_mode": response_payload.get("retrieval_mode", "empty"),
        "source_status": response_payload.get("source_status", "fallback"),
        "evidence": {
            "matched_chunk_count": len(matched_chunks),
            "relevant_chunk_count": relevant_chunks,
            "data_api_call_count": len(data_api_calls),
            "successful_data_api_call_count": completed_calls,
        },
        "metrics": {
            "retrieval_hit_rate": _metric(
                retrieval_hit_rate,
                "Share of retrieval or live-data calls that returned usable evidence.",
            ),
            "context_precision": _metric(
                context_precision,
                "Share of retrieved chunks that overlap the question or pass the relevance threshold.",
            ),
            "answer_relevance": _metric(
                answer_relevance,
                "Lexical similarity proxy between the customer question and final answer.",
            ),
            "groundedness": _metric(
                groundedness,
                "Share of meaningful answer terms supported by retrieved context.",
            ),
            "hallucination_risk": _metric(
                hallucination_risk,
                "Unsupported-answer-term proxy; lower is better.",
                lower_is_better=True,
            ),
            "overall_quality": _metric(
                overall_score,
                "Average of the available online proxy scores.",
            ),
            "context_recall": _metric(
                None,
                "Requires labelled expected source documents for each question.",
            ),
            "mrr": _metric(
                None,
                "Requires a labelled relevant-document rank for each evaluation question.",
            ),
            "ndcg": _metric(
                None,
                "Requires graded relevance labels for retrieved documents.",
            ),
        },
    }
