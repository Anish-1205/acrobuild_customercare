"""Pure honesty checks shared by live discovery acceptance and unit tests."""
import re


_ASSERTIVE_PRICE_RE = re.compile(
    r"\bprices?\s+(?:is|are|was|were|starts?|started|from|at)\b"
    r"|\bpriced\s+(?:at|from)\b"
    r"|\bcosts?\s+(?:is|are|was|were|INR\b|Rs\.?\b|₹|[\d,.])"
    r"|\bavailable\s+(?:at|for)\s+(?:INR\b|Rs\.?\b|₹|[\d,.])",
    re.IGNORECASE,
)
_UNSUPPORTED_AVAILABILITY_RE = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+units?\s+"
    r"(?:are\s+)?(?:currently\s+)?(?:available|listed)\b"
    r"|\bunits?\s+(?:are\s+)?currently\s+available\b",
    re.IGNORECASE,
)


def honesty_problems(turn):
    """Return unsupported factual claims in one captured discovery turn.

    Neutral budget questions may mention prices and show an input-format
    example. Factual price assertions remain disallowed: discovery results use
    recomputable ``estimated base amount`` lines and the required disclaimer.
    """
    answer = str(turn.get("answer") or "")
    discovery_kind = turn.get("discovery_kind")
    problems = []
    if discovery_kind == "results":
        if "estimated base amount" not in answer:
            problems.append("missing 'estimated base amount'")
        if "It is a base estimate only" not in answer:
            problems.append("missing disclaimer")
    if discovery_kind and _ASSERTIVE_PRICE_RE.search(answer):
        problems.append("unsupported property price claim")
    if discovery_kind and _UNSUPPORTED_AVAILABILITY_RE.search(answer):
        problems.append("unsupported unit availability claim")
    if discovery_kind and "floor plan" in answer.lower():
        problems.append("says 'floor plan'")
    return problems
