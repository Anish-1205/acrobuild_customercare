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

# A localized figure keeps its digits; the currency and unit may be translated.
_FIGURE_RE = re.compile(
    r"(?:INR|Rs\.?|₹)\s*([\d.]+)\s*(crore|lakh|करोड़|करोड|लाख)", re.IGNORECASE,
)
_UNIT_NAMES = {"करोड़": "crore", "करोड": "crore", "लाख": "lakh"}
# Translations of the estimate label and of the disclaimer's exclusions.
_LOCALIZED_ESTIMATE_WORDS = ("अनुमान", "अनुमानित")
# "कर" (tax) only counts as a whole word, never inside "करोड़".
_LOCALIZED_TAX_TOKENS = ("कर", "करों", "जीएसटी", "GST")
_LOCALIZED_CHARGE_WORDS = ("टैक्स", "पंजीकरण", "रजिस्ट्रेशन", "शुल्क", "स्टाम्प ड्यूटी", "स्टांप ड्यूटी")
# "केवल"/"सिर्फ" (only) never prove an exclusion; the charges must be excluded or additional.
_LOCALIZED_EXCLUDED_PHRASES = ("शामिल नहीं", "अलग से", "अतिरिक्त", "छोड़कर", "के अलावा")
_TOKEN_SPLIT_RE = re.compile(r"[\s,।.;:()!?\-]+")


def normalize_figure(match):
    """Canonical ``INR <amount> <crore|lakh>`` form of one ``_FIGURE_RE`` match."""
    unit = match.group(2)
    return f"INR {match.group(1)} {_UNIT_NAMES.get(unit, unit.lower())}"


def figures_in(answer):
    """Every INR figure in an answer, normalized to the English form."""
    return [normalize_figure(match) for match in _FIGURE_RE.finditer(str(answer or ""))]


def localized_estimate_lines(answer, project_names):
    """(project, figure) pairs from bullet lines that start with a known project name."""
    pairs = []
    for line in str(answer or "").splitlines():
        if not line.startswith("- "):
            continue
        name = max((n for n in project_names if line[2:].startswith(n)), key=len, default=None)
        match = _FIGURE_RE.search(line)
        if name and match:
            pairs.append((name, normalize_figure(match)))
    return pairs


def _is_localized(answer):
    return any(ord(char) > 127 and char.isalpha() for char in answer)


def _mentions_localized_charges(line):
    tokens = set(_TOKEN_SPLIT_RE.split(line))
    return (any(token in tokens for token in _LOCALIZED_TAX_TOKENS)
            or any(word in line for word in _LOCALIZED_CHARGE_WORDS))


def _has_localized_disclaimer(answer):
    """A non-bullet line: a base estimate whose taxes/charges are excluded or extra."""
    return any(
        not line.startswith("- ")
        and any(word in line for word in _LOCALIZED_ESTIMATE_WORDS)
        and _mentions_localized_charges(line)
        and any(phrase in line for phrase in _LOCALIZED_EXCLUDED_PHRASES)
        for line in answer.splitlines()
    )


def _has_localized_estimate_labels(answer):
    """Every result bullet with a figure carries the translated estimate label."""
    figure_lines = [line for line in answer.splitlines()
                    if line.startswith("- ") and _FIGURE_RE.search(line)]
    return bool(figure_lines) and all(
        any(word in line for word in _LOCALIZED_ESTIMATE_WORDS) for line in figure_lines)


def honesty_problems(turn, expected_figures=None):
    """Return unsupported factual claims in one captured discovery turn.

    Neutral budget questions may mention prices and show an input-format
    example. Factual price assertions remain disallowed: discovery results use
    recomputable ``estimated base amount`` lines and the required disclaimer.
    A localized reply may translate both; ``expected_figures`` maps project
    names to grounded ``INR`` figures that its estimate lines must match.
    """
    answer = str(turn.get("answer") or "")
    discovery_kind = turn.get("discovery_kind")
    problems = []
    if discovery_kind == "results":
        localized = _is_localized(answer)
        if "estimated base amount" not in answer and not (
                localized and _has_localized_estimate_labels(answer)):
            problems.append("missing 'estimated base amount'")
        if "It is a base estimate only" not in answer and not (
                localized and _has_localized_disclaimer(answer)):
            problems.append("missing disclaimer")
        if expected_figures:
            for name, shown in localized_estimate_lines(answer, expected_figures):
                if expected_figures[name] != shown:
                    problems.append(f"figure mismatch for {name}: shown {shown}, "
                                    f"expected {expected_figures[name]}")
    if discovery_kind and _ASSERTIVE_PRICE_RE.search(answer):
        problems.append("unsupported property price claim")
    if discovery_kind and _UNSUPPORTED_AVAILABILITY_RE.search(answer):
        problems.append("unsupported unit availability claim")
    if discovery_kind and "floor plan" in answer.lower():
        problems.append("says 'floor plan'")
    return problems
