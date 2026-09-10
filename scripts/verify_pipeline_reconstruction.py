"""Differential test: reconstructed pipeline source vs the original bytecode.

Loads both the marshalled `.pyc` and `haystack_conversation_pipeline_source.py`
into isolated namespaces (with `search_company_knowledge` /
`generate_qwen_chat_response` stubbed), then compares every function's output
across a large input corpus. Exits non-zero on any mismatch.

Run:  .venv/Scripts/python.exe scripts/verify_pipeline_reconstruction.py
"""
from __future__ import annotations

import marshal
import random
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PYC = ROOT / "graph" / "haystack_conversation_pipeline_runtime.pyc"
SRC = ROOT / "graph" / "haystack_conversation_pipeline_source.py"

# ---- stubs -------------------------------------------------------------------

_PROJECTS_CHUNK = {
    "source_key": "acrobuild-cs-projects",
    "project_names": ["Skyline Residency", "Green Valley", "Ambernath Heights", "Kalyan One"],
    "body_text": "Projects in Ambernath, Kalyan and Thane with 1 and 2 BHK homes near the station.",
    "excerpt": "Ambernath Kalyan Thane station schools",
}


def _stub_search_company_knowledge(query):
    return [_PROJECTS_CHUNK, {"source_key": "acrobuild-cs-company", "body_text": "GBK Group"}]


def _stub_generate_qwen_chat_response(**kwargs):
    # deterministic marker so both sides produce identical output
    return f"QWEN[{kwargs.get('user_prompt', '')!r}|{len(kwargs.get('conversation_messages') or [])}|{kwargs.get('temperature')}]"


def _load_pyc():
    ns: dict = {"__name__": "graph.haystack_conversation_pipeline"}
    code = marshal.loads(PYC.read_bytes()[16:])
    exec(code, ns, ns)
    return ns


def _load_src():
    ns: dict = {"__name__": "graph.haystack_conversation_pipeline"}
    code = compile(SRC.read_text(encoding="utf-8"), str(SRC), "exec")
    exec(code, ns, ns)
    return ns


def _patch(ns):
    ns["search_company_knowledge"] = _stub_search_company_knowledge
    ns["generate_qwen_chat_response"] = _stub_generate_qwen_chat_response


# ---- corpus ----------------------------------------------------------------

ISSUES = [
    "", "  ", "hi", "Hi there!", "hello", "good morning", "good evening.", "thanks", "bye", "okay", "ok",
    "how are you", "what are you doing", "what's up", "tell me a joke", "who are you", "what can you do",
    "fun fact", "weather in Mumbai", "who is the current president", "what is 2+2",
    "prabhas movies", "diagnose my chest pain", "should I invest in stocks", "legal advice please",
    "show me 2 BHK flats in Pune", "find ready to move apartments", "what is the price of flat 1108",
    "do you have anything in Ambernath", "looking for something near good schools",
    "floor 5 details", "1500 sq ft options", "compare Skyline Residency and Green Valley",
    "which project has more floors", "cheapest project", "most expensive unit", "best flat for a family",
    "tell me about this project", "what about that wing", "go with wing A", "choose wing B tower",
    "is this ready to move", "explore Green Valley", "proceed", "yes please", "show me",
    "more detail about the construction status", "possession date for this", "how much is this",
    "what is the construction progress", "wing details for Skyline", "show me the wings",
    "which wings are available", "availability in Kalyan One", "3 bhk in ambernath heights",
    "Ambernath Heights location", "site visit booking", "asdkj qweoi", "???", "a",
    "this that it", "the selected flat cost", "recommend one option", "1 bhk cheapest project",
]

BOT_TEXTS = [
    "", "Would you like to explore Skyline Residency?",
    "Here are the wings:\n- Wing A\n- Wing B Tower\n- Wing C",
    "We have projects in Ambernath. Which project would you like?",
    "Got it - Wing A. Which floor?", "Wing: B Tower selected.",
    "You can explore Green Valley or Kalyan One?", "The 2 BHK in Skyline Residency starts at 75 lakh.",
    "I can help with that.", "Choose a project to continue.",
]


def _messages():
    out = [[]]
    for bot in BOT_TEXTS:
        out.append([{"sender": "bot", "text": bot}])
        out.append([
            {"sender": "customer", "text": "show me projects"},
            {"sender": "bot", "text": bot},
            {"sender": "customer", "text": "and pricing?"},
        ])
    out.append([{"sender": "bot", "text": "Skyline Residency has 12 floors. Green Valley has 9 floors."}])
    return out


ANSWERS = [
    "", "The latest customer message is about pricing.", "You asked about floors.",
    "Skyline Residency has more floors on floor 12.", "The 2 BHK is priced at INR 75 lakh.",
    "Wing A has 10 floors.", "Available inventory: 3 units.", "floor 5 has 2 units at 1500 sq ft.",
    "The cheapest option is Green Valley at the lowest price.", "Green Valley is the most expensive, costliest.",
    "Base rates by project vary across projects.", "3 BHK homes are available.",
    "This project has 2 bhk homes on floor 3 at 1200 sq ft for INR 60 lakh in Skyline Residency.",
]


def main() -> int:
    pyc, src = _load_pyc(), _load_src()
    _patch(pyc)
    _patch(src)

    mismatches = []
    counter = [0]

    def check(name, *args):
        counter[0] += 1
        a = _safe(pyc[name], args)
        b = _safe(src[name], args)
        if a != b:
            mismatches.append((name, args, a, b))

    def _safe(fn, args):
        try:
            return ("ok", fn(*args))
        except Exception as exc:  # noqa: BLE001
            return ("exc", f"{type(exc).__name__}: {exc}")

    unary = [
        "normalize_text", "is_property_support_message", "is_small_talk_message",
        "matches_live_company_context", "is_live_information_question",
        "is_high_stakes_general_question", "is_unclear_general_message",
        "build_deterministic_conversation_answer",
    ]
    for issue in ISSUES:
        for name in unary:
            check(name, issue)
    check("normalize_text", None)
    check("normalize_text", 123)
    check("normalize_text", ["a", "b"])

    msgs = _messages()
    for cm in msgs:
        check("_latest_bot_message", cm)
        check("_conversation_project_name", cm)
        check("get_live_project_names")
        for issue in ISSUES:
            check("_selected_wing_from_context", issue, cm)
            check("resolve_contextual_support_issue", issue, cm)
            check("is_contextual_property_reply", issue, cm)
            check("build_local_conversation_answer", issue, cm)

    for issue in ISSUES:
        for answer in ANSWERS:
            check("validate_general_answer", issue, answer)
            check("validate_support_answer", issue, answer)

    for issue in ISSUES[:20]:
        for cm in msgs[:8]:
            state = {"issue": issue, "conversation_messages": cm}
            check("classify_conversation_route", state)
            check("select_route", {**state, "route": "support"})
            check("conversation_node", state)
            check("validate_support_node", {"issue": issue, "response": {"answer": random.choice(ANSWERS)}})
            check("support_node", {**state, "support_handler": lambda: {"answer": "handled"}})

    # fuzz
    rng = random.Random(20260910)
    alphabet = "abcdefghijklmnop 123 bhk floor project wing .!?-"
    for _ in range(400):
        issue = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        for name in unary:
            check(name, issue)
        cm = rng.choice(msgs)
        check("resolve_contextual_support_issue", issue, cm)
        check("is_contextual_property_reply", issue, cm)
        check("validate_support_answer", issue, rng.choice(ANSWERS))

    if mismatches:
        print(f"MISMATCHES: {len(mismatches)} / {counter[0]} cases")
        for name, args, a, b in mismatches[:40]:
            print(f"\n  {name}{args!r}\n    pyc: {a!r}\n    src: {b!r}")
        return 1
    print(f"OK - reconstructed source matches the bytecode across {counter[0]} cases, 0 mismatches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
