"""Readable multi-turn property calculations used after answer generation."""
from __future__ import annotations

import re
from typing import Any


def _normalize(value: object) -> str:
    return " ".join(str(value or "").split())


def _parse_number(value: object) -> float | None:
    try:
        return float(str(value or "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _format_inr(value: float) -> str:
    return f"INR {value:,.0f}"


def build_contextual_flat_cost_answer(
    cleaned_issue: str,
    conversation_messages: list[dict[str, Any]] | None,
) -> str | None:
    """Calculate a referenced flat's base amount from prior grounded details."""
    explicitly_refers_to_flat = bool(re.search(
        r"\b(?:this|that|the|selected|above)\s+(?:flat|unit|home)\b", cleaned_issue,
    ))
    bare_reference = bool(re.fullmatch(
        r"(?:so\s+)?how much(?:\s+(?:is|does|will|would))?\s+(?:this|that|it)(?:\s+cost)?\??",
        cleaned_issue.strip(),
    ))
    asks_total_cost = any(phrase in cleaned_issue for phrase in (
        "total cost", "total price", "cost of", "price of",
        "how much is", "how much will", "what will it cost",
    )) or bool(re.search(
        r"\b(?:how much\b.{0,30}\b(?:flat|unit|home)\b|(?:flat|unit|home)\b.{0,12}\b(?:cost|price))",
        cleaned_issue,
    ))
    if not (explicitly_refers_to_flat or bare_reference) or not asks_total_cost:
        return None

    messages = list(conversation_messages or [])
    flat_number = ""
    for message in reversed(messages):
        text = _normalize(message.get("text"))
        match = re.search(r"\bflat\s*[:#-]?\s*(\d+[a-z0-9-]*)\b", text, flags=re.IGNORECASE)
        if match:
            flat_number = match.group(1)
            break

    for message in reversed(messages):
        if _normalize(message.get("sender")).lower() not in {"bot", "assistant", "agent"}:
            continue
        text = _normalize(message.get("text"))
        if flat_number and not re.search(
            rf"\bflat\s*[:#-]?\s*{re.escape(flat_number)}\b", text, flags=re.IGNORECASE,
        ):
            continue
        area_match = re.search(
            r"saleable\s+area\s*:\s*([\d,.]+)\s*(?:sq\.?\s*ft|sqft)", text, flags=re.IGNORECASE,
        )
        rate_match = re.search(
            r"(?:live|base)?\s*(?:price|rate)\s*:\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)\s*"
            r"(?:-|–|to)\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)",
            text,
            flags=re.IGNORECASE,
        )
        if not area_match or not rate_match:
            continue
        area = _parse_number(area_match.group(1))
        minimum_rate = _parse_number(rate_match.group(1))
        maximum_rate = _parse_number(rate_match.group(2))
        if not area or not minimum_rate or not maximum_rate:
            continue
        label = f"Flat {flat_number}" if flat_number else "This flat"
        return (
            f"For {label}, the estimated base cost is {_format_inr(area * minimum_rate)} to "
            f"{_format_inr(area * maximum_rate)} ({area:g} sq. ft. × {_format_inr(minimum_rate)}–"
            f"{_format_inr(maximum_rate)} per sq. ft.).\n\n"
            "This is a base-price estimate, not the final all-inclusive total. Taxes, registration, "
            "floor-rise, parking, maintenance, and other charges may apply; please request the current "
            "cost sheet for the final amount."
        )
    return None


def build_contextual_same_price_floor_answer(
    cleaned_issue: str,
    matched_chunks: list[dict[str, Any]] | None,
    conversation_messages: list[dict[str, Any]] | None,
) -> str | None:
    asks_same_price = any(phrase in cleaned_issue for phrase in (
        "same price", "same cost", "same rate", "similar price", "similar cost",
    ))
    floor_match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+floor\b", cleaned_issue)
    if not asks_same_price or not floor_match:
        return None

    target_floor = int(floor_match.group(1))
    messages = list(conversation_messages or [])
    reference_text = ""
    for message in reversed(messages):
        text = _normalize(message.get("text"))
        if (
            re.search(r"\bflat\s*[:#-]?\s*\d+", text, flags=re.IGNORECASE)
            and "saleable area" in text.lower()
            and re.search(r"(?:live|base)?\s*(?:price|rate)\s*:", text, flags=re.IGNORECASE)
        ):
            reference_text = text
            break
    if not reference_text:
        return None

    flat_match = re.search(r"\bflat\s*[:#-]?\s*(\d+[a-z0-9-]*)\b", reference_text, flags=re.IGNORECASE)
    area_match = re.search(r"saleable\s+area\s*:\s*([\d,.]+)", reference_text, flags=re.IGNORECASE)
    rate_match = re.search(
        r"(?:live|base)?\s*(?:price|rate)\s*:\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)\s*"
        r"(?:-|–|to)\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)",
        reference_text,
        flags=re.IGNORECASE,
    )
    type_match = re.search(r"\b([1-5]\s*BHK(?:\+T)?)\b", reference_text, flags=re.IGNORECASE)
    if not flat_match or not area_match or not rate_match:
        return None

    reference_flat = flat_match.group(1)
    reference_area = _parse_number(area_match.group(1))
    minimum_rate = _parse_number(rate_match.group(1))
    maximum_rate = _parse_number(rate_match.group(2))
    reference_type = re.sub(r"\s+", "", type_match.group(1)).lower() if type_match else ""
    if not reference_area or not minimum_rate or not maximum_rate:
        return None

    history_text = " ".join(_normalize(message.get("text")) for message in messages)
    project_chunks = [
        chunk for chunk in (matched_chunks or [])
        if _normalize(chunk.get("project_name")) and chunk.get("inventory_loaded")
    ]
    selected_project = next(
        (
            chunk for chunk in reversed(project_chunks)
            if _normalize(chunk.get("project_name")).lower() in history_text.lower()
        ),
        None,
    )
    if selected_project is None:
        return None

    matches = []
    for unit in selected_project.get("available_inventory", []) or []:
        try:
            unit_floor = int(unit.get("floorNumber"))
        except (TypeError, ValueError):
            continue
        unit_area = _parse_number(unit.get("saleableArea"))
        unit_type = re.sub(r"\s+", "", _normalize(unit.get("typologyType"))).lower()
        if unit_floor != target_floor or unit_area != reference_area:
            continue
        if reference_type and unit_type and unit_type != reference_type:
            continue
        matches.append(unit)

    project_name = _normalize(selected_project.get("project_name")) or "the selected project"
    if not matches:
        return (
            f"No currently available flat on floor {target_floor} in {project_name} matches Flat "
            f"{reference_flat}'s configuration and {reference_area:g} sq. ft. saleable area at the same "
            "listed rate. I can check the closest available size or price on that floor instead."
        )

    unit_labels = list(dict.fromkeys(str(unit.get("unitNumber") or unit.get("id")) for unit in matches))
    return (
        f"Yes. On floor {target_floor} in {project_name}, the matching available "
        f"flat{'s are' if len(unit_labels) != 1 else ' is'} "
        f"{', '.join('Flat ' + label for label in unit_labels)}. "
        f"{'They have' if len(unit_labels) != 1 else 'It has'} the same {reference_area:g} sq. ft. "
        f"saleable area and listed rate of {_format_inr(minimum_rate)}–{_format_inr(maximum_rate)} per "
        f"sq. ft., giving the same estimated base-cost range of "
        f"{_format_inr(reference_area * minimum_rate)}–{_format_inr(reference_area * maximum_rate)}. "
        "Availability and the final cost sheet should be confirmed before booking."
    )
