"""Reconstructed source for the Haystack conversation runtime.

This is a hand-reconstruction of ``haystack_conversation_pipeline_runtime.pyc``
(bytecode-only, no original source). It is loaded by
``graph/haystack_conversation_pipeline.py`` in preference to marshalling the
``.pyc`` — see ``docs/RECONSTRUCTION_STATUS.md``.

The loader ``exec``s this file into its own module globals (exactly as it did
the bytecode), so the wrapper overrides in that loader
(``build_deterministic_conversation_answer``, ``is_small_talk_message``,
``resolve_contextual_support_issue``, ``validate_support_node``) still apply to
the pipeline defined here.

Verified against the bytecode by differential testing — see
``scripts/verify_pipeline_reconstruction.py``.
"""
import os
import re
from typing import Any, Callable, TypedDict

os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")

from haystack import Pipeline, component

from qwen import generate_qwen_chat_response
from services.acrobuild_company_service import search_company_knowledge


class ConversationState(TypedDict, total=False):
    issue: str
    conversation_messages: list[dict[str, str]]
    route: str
    response: dict[str, Any]
    support_handler: Callable[[], dict[str, Any]]


PROPERTY_SUPPORT_TERMS = frozenset({
    "acrobuild", "address", "agent", "amenities", "amenity", "apartment", "apartments",
    "availability", "available", "bhk", "book", "booking", "complaint", "configuration",
    "construction", "cost", "document", "documents", "flat", "flats", "floor", "handover",
    "home", "homes", "inventory", "location", "maintenance", "payment", "plot", "plots",
    "possession", "price", "pricing", "project", "projects", "properties", "property",
    "rate", "rates", "refund", "rera", "site visit", "size", "sq ft", "sq.ft", "support",
    "ticket", "tower", "unit", "units", "villa", "villas", "wing",
    # Romanized Indian-language words for home/price (fallback routing only; the
    # LLM turn analyzer is the primary router).
    "ghar", "makaan", "makan", "illu", "veedu", "keemat", "kimat", "daam", "dhara", "vilai",
})

# Whole-word/phrase matching — a plain substring check let "unit" match inside
# "united" (e.g. "president of the united states"), misrouting ordinary general
# questions into the property assistant.
_PROPERTY_SUPPORT_TERM_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in PROPERTY_SUPPORT_TERMS) + r")\b"
)

SMALL_TALK_PATTERNS = (
    r"^(?:hi|hello|hey|good morning|good afternoon|good evening)[!. ]*$",
    r"\bhow are you\b",
    r"\bwhat are you doing\b",
    r"\bwhat(?:'s| is) up\b",
    r"\b(?:tell|share|give) me (?:a )?joke\b",
    r"\bmake me laugh\b",
    r"\bwho are you\b",
    r"\bwhat can you do\b",
    r"\b(?:tell|write) me (?:a )?story\b",
    r"\bfun fact\b",
    r"\bwhat do you think\b",
    r"\bcan we chat\b",
    r"\bwhat(?:'s| is) your favorite\b",
    r"\bweather\b",
    r"^(?:thanks|thank you|bye|goodbye|okay|ok)[!. ]*$",
)


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def is_property_support_message(issue: str) -> bool:
    cleaned = normalize_text(issue).lower()
    if not cleaned:
        return False
    natural_location_search = bool(re.search(
        r"\b(?:do you have|show me|find|looking for|need)\s+(?:anything|something|options?)\s+(?:in|near|around)\b",
        cleaned,
    ))
    return (
        bool(_PROPERTY_SUPPORT_TERM_RE.search(cleaned))
        or natural_location_search
        or bool(re.search(r"\b[1-6]\s*bhk\b|\bfloor\s*\d+\b|\b\d{3,5}\s*sq", cleaned))
    )


def is_small_talk_message(issue: str) -> bool:
    cleaned = normalize_text(issue).lower()
    return any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in SMALL_TALK_PATTERNS)


# Generic real-estate marketing words that commonly form part of a project name
# (e.g. "Vishwajeet Prime", "Thane Heights") but are also ordinary English words.
# A bare token match on these alone ("prime minister", "grand total") produced
# false positives that routed plain general-knowledge questions into the
# property assistant, which then refused them outright.
_GENERIC_PROJECT_NAME_WORDS = frozenset({
    "prime", "heights", "elite", "grand", "royal", "empire", "park", "palace",
    "square", "central", "gardens", "greens", "woods", "towers", "tower",
    "residency", "enclave", "view", "vista", "homes", "home", "hills", "valley",
    "meadows", "regency", "plaza", "court", "manor", "paradise", "complex",
    "phase", "crown", "pearl", "orchid", "sapphire", "emerald", "county",
    "town", "group", "precious", "space",
})


def matches_live_company_context(issue: str) -> bool:
    cleaned = normalize_text(issue).lower()
    tokens = {
        token for token in re.findall(r"[a-z0-9]+", cleaned)
        if len(token) >= 4
        if token not in frozenset({
            "when", "which", "where", "tell", "something", "there", "what", "want",
            "anything", "show", "please", "give", "have", "about",
        })
    }
    if not tokens:
        return False
    try:
        chunks = search_company_knowledge("all projects")
    except Exception:
        return False
    project_chunk = next(
        (chunk for chunk in chunks if normalize_text(chunk.get("source_key", "")) == "acrobuild-cs-projects"),
        None,
    )
    if not project_chunk:
        return False
    project_names = [normalize_text(name).lower() for name in project_chunk.get("project_names", [])]
    # A full project name appearing in the message is an unambiguous match.
    if any(project_name and project_name in cleaned for project_name in project_names):
        return True
    # A single generic word (e.g. "prime") is not distinctive enough on its own.
    distinctive_tokens = tokens - _GENERIC_PROJECT_NAME_WORDS
    project_words = {word for name in project_names for word in re.findall(r"[a-z0-9]+", name)}
    if distinctive_tokens & project_words:
        return True
    if re.search(r"\b(?:in|near|around|at)\b", cleaned):
        catalogue_words = set(re.findall(r"[a-z0-9]+", normalize_text(
            project_chunk.get("body_text", "") or project_chunk.get("excerpt", "")
        ).lower()))
        return bool(distinctive_tokens & catalogue_words)
    return False


def _latest_bot_message(conversation_messages: list[dict[str, str]]) -> str:
    return next(
        (
            str(message.get("text", "") or "").strip()
            for message in reversed(conversation_messages)
            if normalize_text(message.get("sender", "")).lower() == "bot"
            and normalize_text(message.get("text", ""))
        ),
        "",
    )


def _conversation_project_name(conversation_messages: list[dict[str, str]]) -> str:
    project_names = get_live_project_names()
    for message in reversed(conversation_messages):
        message_text = normalize_text(message.get("text", "")).lower()
        mentioned = [name for name in project_names if name.lower() in message_text]
        if len(mentioned) == 1:
            return mentioned[0]
        if len(mentioned) > 1:
            continue
    return ""


def _selected_wing_from_context(issue: str, conversation_messages: list[dict[str, str]]) -> str:
    cleaned_issue = normalize_text(issue).lower().strip(" .!?")
    latest_bot_text = _latest_bot_message(conversation_messages)

    wing_options = [
        normalize_text(name)
        for name in re.findall(r"(?m)^\s*[-*]\s*([^:\n]+)(?::|$)", latest_bot_text)
        if normalize_text(name)
    ]

    selection_match = re.search(
        r"\b(?:go with|go for|choose|select|take|pick)\s+(?:the\s+)?(?:wing\s+)?([a-z0-9]+(?:\s+[a-z0-9]+)?)\b",
        cleaned_issue,
    )
    if selection_match and wing_options:
        selection = selection_match.group(1).strip()
        exact = next((option for option in wing_options if option.lower() == selection), "")
        if exact:
            return exact
        suffix = next(
            (option for option in wing_options if option.lower().split()[-1] == selection.split()[-1]),
            "",
        )
        if suffix:
            return suffix

    transcript = "\n".join(str(message.get("text", "") or "") for message in conversation_messages[-8:])
    known_wing = re.findall(
        r"(?:\bWing:\s*|\bin\s+|\bGot it\s*-\s*)([A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+){0,2})\s+wing\b",
        transcript,
        flags=re.IGNORECASE,
    )
    if known_wing:
        return normalize_text(known_wing[-1])
    return ""


def resolve_contextual_support_issue(issue: str, conversation_messages: list[dict[str, str]]) -> str:
    cleaned_issue = normalize_text(issue)
    if not is_contextual_property_reply(issue, conversation_messages):
        return cleaned_issue

    project_name = _conversation_project_name(conversation_messages)
    selected_wing = _selected_wing_from_context(issue, conversation_messages)

    references_project = bool(re.search(
        r"\b(?:this|that|selected|same|recommended)\s+(?:project|property)\b", cleaned_issue, flags=re.IGNORECASE,
    ))
    references_wing = bool(re.search(
        r"\b(?:this|that|selected|same|recommended)\s+wing\b", cleaned_issue, flags=re.IGNORECASE,
    ))
    references_specific_non_project_entity = bool(re.search(
        r"\b(?:this|that|selected|same|recommended)\s+(?:wing|floor|flat|home|unit|option)\b",
        cleaned_issue, flags=re.IGNORECASE,
    ))
    bare_reference = bool(re.search(r"\b(?:this|that|it)\b", cleaned_issue, flags=re.IGNORECASE))

    if (references_project and not references_wing) or (
        bare_reference and not references_specific_non_project_entity
    ):
        selected_wing = ""

    latest_bot_text = _latest_bot_message(conversation_messages)
    project_match = re.search(r"\bexplore\s+(.+?)(?:\?|$)", latest_bot_text, flags=re.IGNORECASE)
    if not project_name and project_match:
        project_name = project_match.group(1).strip()

    scope_parts = []
    if selected_wing:
        scope_parts.append(f"{selected_wing} wing")
    if project_name:
        scope_parts.append(f"in {project_name}" if selected_wing else project_name)
    scope = " ".join(scope_parts)

    if any(term in cleaned_issue.lower() for term in ("construction", "progress", "status", "possession")):
        if scope:
            return f"Show verified construction status for {scope}"
        return cleaned_issue

    referential_question = bool(re.search(
        r"\b(?:this|that|selected|same|recommended)\s+(?:project|property|wing|floor|flat|home|unit|option)\b"
        r"|\b(?:it|this|that)\b",
        cleaned_issue, flags=re.IGNORECASE,
    ))
    if scope and referential_question:
        resolved = re.sub(
            r"\b(?:this|that|selected|same|recommended)\s+(?:project|property)\b",
            f"project {project_name}" if project_name else scope,
            cleaned_issue, flags=re.IGNORECASE,
        )
        resolved = re.sub(
            r"\b(?:this|that|selected|same|recommended)\s+wing\b",
            f"{selected_wing} wing" if selected_wing else scope,
            resolved, flags=re.IGNORECASE,
        )
        if bare_reference and project_name and not references_specific_non_project_entity:
            resolved = re.sub(
                r"\b(?:this|that|it)\b", f"project {project_name}", resolved, flags=re.IGNORECASE,
            )
        if scope.lower() not in resolved.lower():
            resolved = f"{resolved} for {scope}"
        return resolved

    if scope:
        return f"Show verified details for {scope}"
    return cleaned_issue


def is_contextual_property_reply(issue: str, conversation_messages: list[dict[str, str]]) -> bool:
    cleaned_issue = normalize_text(issue).lower().strip(" .!?")
    affirmative = cleaned_issue in frozenset({
        "okay", "ok", "proceed", "show me", "yep", "yeah", "yes please", "sure", "please do", "yes",
    })
    selection = bool(re.search(
        r"\b(?:go with|go for|choose|select|take|pick)\s+(?:the\s+)?(?:wing\s+)?[a-z0-9]+", cleaned_issue,
    ))
    contextual_detail = any(term in cleaned_issue for term in (
        "more detail", "details about", "special about", "tell me about",
        "construction process", "construction status", "progress", "possession",
    ))
    referential_question = bool(re.search(
        r"\b(?:this|that|it)\b"
        r"|\b(?:selected|same|recommended)\s+(?:project|property|wing|floor|flat|home|unit|option)\b",
        cleaned_issue,
    ))
    if not (affirmative or selection or contextual_detail or referential_question):
        return False

    previous_bot_text = _latest_bot_message(conversation_messages).lower()
    if not previous_bot_text:
        return False

    property_context = (
        is_property_support_message(previous_bot_text)
        or "explore" in previous_bot_text
        or matches_live_company_context(previous_bot_text)
    )
    asks_to_continue = any(phrase in previous_bot_text for phrase in (
        "would you like", "do you want", "shall i", "choose a", "select a",
        "which project", "which wing", "which floor", "explore", "proceed",
    ))
    return property_context and (
        asks_to_continue or selection or contextual_detail or referential_question
    )


def classify_conversation_route(state: ConversationState) -> ConversationState:
    issue = normalize_text(state.get("issue", ""))
    conversation_messages = state.get("conversation_messages", [])
    if (
        is_property_support_message(issue)
        or matches_live_company_context(issue)
        or is_contextual_property_reply(issue, conversation_messages)
    ):
        route = "support"
    else:
        route = "conversation"
    return {**state, "route": route}


def select_route(state: ConversationState) -> str:
    return state.get("route", "support")


JOKE_RESPONSE = (
    "Why did the building bring a ladder to the meeting? "
    "Because it wanted to take the discussion to the next level."
)

LIVE_INFORMATION_PATTERNS = (
    r"\b(?:today|right now|currently|current|latest|live|this week|this month)\b",
    r"\b(?:weather|temperature|forecast|score|scores|news|stock price|exchange rate)\b",
    r"\bwho is (?:the )?(?:current )?(?:president|prime minister|chief minister|ceo)\b",
)

HIGH_STAKES_PATTERNS = (
    r"\b(?:diagnose|diagnosis|dosage|dose|medicine|medical emergency|suicid)\w*\b",
    r"\b(?:legal advice|lawsuit|sue|criminal charge|court deadline)\b",
    r"\b(?:invest|investment|buy stock|sell stock|tax advice|financial advice)\b",
)


def is_live_information_question(issue: str) -> bool:
    cleaned = normalize_text(issue).lower()
    return any(re.search(pattern, cleaned) for pattern in LIVE_INFORMATION_PATTERNS)


def is_high_stakes_general_question(issue: str) -> bool:
    cleaned = normalize_text(issue).lower()
    return any(re.search(pattern, cleaned) for pattern in HIGH_STAKES_PATTERNS)


def is_unclear_general_message(issue: str) -> bool:
    cleaned = normalize_text(issue).lower().strip(" .!?")
    tokens = re.findall(r"[a-z0-9]+", cleaned)
    return (
        bool(cleaned)
        and len(tokens) == 1
        and cleaned not in frozenset({"okay", "ok", "hey", "hello", "bye", "thanks", "goodbye", "hi"})
    )


def validate_general_answer(issue: str, answer: str) -> str:
    cleaned_issue = normalize_text(issue)
    cleaned_answer = normalize_text(answer)
    if not cleaned_answer or cleaned_answer.lower() == cleaned_issue.lower():
        return "I could not form a reliable answer. Could you rephrase the question with a little more detail?"
    if "acrobuild" not in cleaned_issue.lower() and any(phrase in cleaned_answer.lower() for phrase in (
        "acrobuild technology", "work with acrobuild", "through acrobuild", "at acrobuild", "acrobuild-related",
    )):
        return (
            "I do not have reliable information connecting that subject to Acrobuild. "
            "Please ask the general question again and I will answer without making that connection."
        )
    return cleaned_answer


def build_deterministic_conversation_answer(issue: str) -> str:
    cleaned = normalize_text(issue).lower().strip(" .!?")
    if is_unclear_general_message(issue):
        return "Could you add a little more detail so I can understand exactly what you want to know?"
    if is_live_information_question(issue):
        return (
            "I do not have live internet access, so I cannot reliably confirm current information for that "
            "question. If you share a source or the relevant details, I can help explain or analyze them."
        )
    if is_high_stakes_general_question(issue):
        return (
            "I can provide general educational information, but I cannot safely give a definitive medical, "
            "legal, or financial decision from this chat alone. Please share the topic and context, and verify "
            "any action with an appropriately qualified professional."
        )
    if "prabhas" in cleaned:
        return (
            "Yes. Prabhas is an Indian film actor who works mainly in Telugu cinema. He is best known "
            "internationally for starring as Amarendra and Mahendra Baahubali in the Baahubali films, and has "
            "also starred in films including Saaho, Salaar, and Kalki 2898 AD."
        )
    if "how are you" in cleaned:
        return "I'm doing well, thank you! How are you, and what would you like to talk about?"
    if "what are you doing" in cleaned or re.search(r"\bwhat(?:'s| is) up\b", cleaned):
        return "I'm here and ready to chat with you. What's on your mind?"
    if re.search(r"(?:tell|share|give) me (?:a )?joke|make me laugh", cleaned):
        return JOKE_RESPONSE
    if "who are you" in cleaned:
        return (
            "I'm the Acrobuild Assistant. I can chat with you and help with live project, availability, "
            "pricing, document, handover, and site-visit questions."
        )
    if "what can you do" in cleaned:
        return (
            "I can have a normal conversation and also check live Acrobuild project details, wings, floors, "
            "available homes, pricing, and site visits."
        )
    if cleaned in frozenset({"hey", "hello", "hello there", "hey there", "hi there", "hi"}):
        return "Hi! It's nice to hear from you. How can I help?"
    if cleaned in frozenset({"good afternoon", "good evening", "good morning"}):
        return f"{cleaned.title()}! How can I help?"
    if cleaned in frozenset({"thanks", "thank you"}):
        return "You're welcome!"
    if cleaned in frozenset({"goodbye", "bye"}):
        return "Goodbye! Have a great day."
    if cleaned in frozenset({"okay", "ok"}):
        return "Okay. What would you like to discuss next?"
    return ""


def build_local_conversation_answer(issue: str, conversation_messages: list[dict[str, str]]) -> str:
    deterministic_answer = build_deterministic_conversation_answer(issue)
    if deterministic_answer:
        return deterministic_answer
    try:
        answer = generate_qwen_chat_response(
            system_prompt=(
                "You are a helpful general-purpose conversational assistant inside the Acrobuild chat. "
                "Answer the user's actual question directly in 1 to 3 short, plain sentences, with no lists, "
                "emojis, filler, or offers of further help. General questions do "
                "not need to be related to Acrobuild. Never invent a connection between a person or topic and "
                "Acrobuild. Use facts you know confidently; never fabricate names, titles, dates, quotations, "
                "film credits, or other specifics. If you are unsure, say what you cannot verify instead of "
                "guessing. Do not claim live or current knowledge. For Acrobuild property facts, explain that "
                "the support tools must be used."
            ),
            user_prompt=issue,
            conversation_messages=conversation_messages[-10:],
            temperature=0.2,
        )
        return validate_general_answer(issue, answer)
    except Exception:
        return (
            "I'm happy to chat. I may not have reliable real-time information for that topic, but you can ask "
            "me conversational questions or anything about Acrobuild support."
        )


def conversation_node(state: ConversationState) -> ConversationState:
    issue = normalize_text(state.get("issue", ""))
    deterministic_answer = build_deterministic_conversation_answer(issue)
    answer = deterministic_answer or build_local_conversation_answer(
        issue, state.get("conversation_messages", []),
    )
    response = {
        "agent_mode": "conversation_haystack",
        "answer": answer,
        "confidence_label": "high",
        "source_label": "Local conversational model",
        "source_status": "conversation",
        "related_articles": [],
        "used_llm": not bool(deterministic_answer),
    }
    return {**state, "response": response}


def support_node(state: ConversationState) -> ConversationState:
    handler = state.get("support_handler")
    if not callable(handler):
        raise RuntimeError("Haystack conversation support handler is unavailable.")
    return {**state, "response": handler()}


def get_live_project_names() -> list[str]:
    try:
        chunks = search_company_knowledge("all projects")
    except Exception:
        return []
    project_chunk = next(
        (chunk for chunk in chunks if normalize_text(chunk.get("source_key", "")) == "acrobuild-cs-projects"),
        None,
    )
    return [
        normalize_text(name)
        for name in (project_chunk or {}).get("project_names", [])
        if normalize_text(name)
    ]


def validate_support_answer(issue: str, answer: str) -> list[str]:
    cleaned_issue = normalize_text(issue).lower()
    cleaned_answer = normalize_text(answer).lower()
    if not cleaned_answer:
        return ["empty answer"]

    failures = []
    if any(cleaned_answer.startswith(prefix) for prefix in (
        "the latest customer message is", "latest customer message:", "the customer asked",
        "you asked", "your question is",
    )):
        failures.append("a direct answer instead of repeating the question")

    asks_floor_project_comparison = (
        "floor" in cleaned_issue
        and "project" in cleaned_issue
        and any(term in cleaned_issue for term in (
            "more", "most", "higher", "highest", "maximum", "fewer", "fewest", "least", "compare",
        ))
    )
    if asks_floor_project_comparison:
        known_projects = get_live_project_names()
        names_a_project = any(name.lower() in cleaned_answer for name in known_projects)
        gives_floor_result = "floor" in cleaned_answer and bool(re.search(r"\b\d+\b", cleaned_answer))
        if not names_a_project or not gives_floor_result:
            failures.append("a verified project floor comparison")

    bhk_match = re.search(r"\b([1-6])\s*bhk\b", cleaned_issue)
    if bhk_match and not re.search(rf"\b{bhk_match.group(1)}\s*bhk\b", cleaned_answer):
        failures.append(f"{bhk_match.group(1)} BHK")

    floor_match = re.search(
        r"\b(?:floor\s*)?(\d{1,3})(?:st|nd|rd|th)?\s*floor\b", cleaned_issue,
    ) or re.search(r"\bfloor\s*(\d{1,3})\b", cleaned_issue)
    if floor_match:
        floor_number = floor_match.group(1)
        if not re.search(
            rf"\bfloor\s*:?\s*{floor_number}\b|\b{floor_number}(?:st|nd|rd|th)\s*floor\b", cleaned_answer,
        ):
            failures.append(f"floor {floor_number}")

    size_match = re.search(r"\b(\d{3,5})\s*(?:sq(?:uare)?\.?\s*ft\.?)", cleaned_issue)
    if size_match and not re.search(rf"\b{size_match.group(1)}\b", cleaned_answer):
        failures.append(f"{size_match.group(1)} sq. ft.")

    explicit_projects = [
        project_name for project_name in get_live_project_names()
        if project_name.lower() in cleaned_issue
    ]
    if explicit_projects and not any(project.lower() in cleaned_answer for project in explicit_projects):
        failures.append("requested project")

    if any(term in cleaned_issue for term in (
        "cheapest", "lowest price", "least expensive", "most affordable",
    )) and not any(term in cleaned_answer for term in (
        "lowest", "cheapest", "affordable", "best-value",
    )):
        failures.append("lowest-price comparison")

    if any(term in cleaned_issue for term in (
        "highest price", "most expensive", "costliest", "maximum price",
    )) and not any(term in cleaned_answer for term in (
        "highest", "most expensive", "costliest", "maximum",
    )):
        failures.append("highest-price comparison")

    asks_for_one_best = any(phrase in cleaned_issue for phrase in (
        "best flat", "best option", "best home", "best unit", "recommend one", "suggest one", "one best",
    ))
    if asks_for_one_best and any(phrase in cleaned_answer for phrase in (
        "base rates by project", "available by project", "across projects", "which project would",
    )):
        failures.append("one recommended option")

    # "cost"/"price"/"rate"/"how much" are common outside real estate too (e.g. "cost
    # of living"), so only require an INR-denominated answer when the question also
    # shows some property-specific signal — otherwise this fires on ordinary general
    # questions and overrides a perfectly good answer with a confusing clarification.
    has_property_pricing_context = bool(
        bhk_match or floor_match or size_match or explicit_projects
        or any(term in cleaned_issue for term in (
            "flat", "flats", "apartment", "apartments", "villa", "villas", "wing",
            "shop", "shops", "unit", "units", "acrobuild", "project", "projects",
            "property", "properties", "tower",
        ))
    )
    if has_property_pricing_context and any(term in cleaned_issue for term in (
        "price", "pricing", "cost", "rate", "how much",
    )) and not any(term in cleaned_answer for term in (
        "inr", "rs.", "rupee", "price", "rate", "value",
    )):
        failures.append("pricing")

    asks_for_wing_details = bool(re.search(
        r"\b(?:wing details?|show (?:me )?(?:the )?wings?|list (?:the )?wings?|which wings?|what wings?)\b",
        cleaned_issue,
    ))
    if asks_for_wing_details and "wing" not in cleaned_answer:
        failures.append("wing details")

    asks_for_availability = any(term in cleaned_issue for term in (
        "available", "availability", "inventory",
    )) and not any(term in cleaned_issue for term in (
        "price", "pricing", "cost", "rate", "how much",
    ))
    if asks_for_availability and not any(term in cleaned_answer for term in (
        "available", "availability", "inventory",
    )):
        failures.append("availability")

    return list(dict.fromkeys(failures))


def validate_support_node(state: ConversationState) -> ConversationState:
    response = dict(state.get("response") or {})
    issue = normalize_text(state.get("issue", ""))
    failures = validate_support_answer(issue, response.get("answer", ""))
    if not failures:
        return {**state, "response": response}
    constraint_text = ", ".join(failures)
    response.update({
        "agent_mode": "relevance_clarification",
        "answer": (
            "I could not verify one live answer that matches all of your requested details: "
            f"{constraint_text}. I will not substitute unrelated project or property data. Please confirm the "
            "detail you want me to relax, or ask me to check the closest live match."
        ),
        "confidence_label": "low",
        "source_label": "Conversation relevance guard",
        "source_status": "clarification",
        "related_articles": [],
        "used_llm": False,
    })
    return {**state, "response": response}


@component
class ConversationOrchestrator:
    """Route and execute one chatbot turn inside a Haystack pipeline."""

    @component.output_types(response=dict)
    def run(
        self,
        issue: str,
        conversation_messages: list[dict[str, str]],
        support_handler: Callable[[], dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        state = {
            "issue": normalize_text(issue),
            "conversation_messages": conversation_messages,
            "support_handler": support_handler,
        }
        routed_state = classify_conversation_route(state)
        if select_route(routed_state) == "conversation":
            completed_state = conversation_node(routed_state)
        else:
            completed_state = validate_support_node(support_node(routed_state))
        return {"response": completed_state["response"]}


def build_conversation_pipeline() -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component("orchestrator", ConversationOrchestrator())
    return pipeline


CONVERSATION_PIPELINE = build_conversation_pipeline()


def run_conversation_pipeline(issue, conversation_messages=None, support_handler=None):
    result = CONVERSATION_PIPELINE.run({"orchestrator": {
        "issue": normalize_text(issue),
        "conversation_messages": conversation_messages or [],
        "support_handler": support_handler,
    }})
    return result["orchestrator"]["response"]
