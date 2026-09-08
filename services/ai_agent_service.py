"""Recovered runtime loader plus deterministic intent fixes."""
from pathlib import Path as _Path
import marshal as _marshal
import re as _re
from services.acrobuild_company_service import resolve_project_from_text
_runtime_path = _Path(__file__).with_name("ai_agent_service_runtime.pyc")
with _runtime_path.open("rb") as _runtime_file:
    _runtime_file.read(16)
    _runtime_code = _marshal.load(_runtime_file)
exec(_runtime_code, globals(), globals())
_legacy_build_company_api_direct_answer = build_company_api_direct_answer


def _parse_number(value):
    try:
        return float(str(value or "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _format_inr(value):
    return f"INR {value:,.0f}"


def _build_contextual_flat_cost_answer(cleaned_issue, conversation_messages):
    """Calculate a referenced flat's base amount from its latest chat details."""
    explicitly_refers_to_flat = bool(_re.search(
        r"\b(?:this|that|the|selected|above)\s+(?:flat|unit|home)\b",
        cleaned_issue,
    ))
    bare_reference = bool(_re.fullmatch(
        r"(?:so\s+)?how much(?:\s+(?:is|does|will|would))?\s+(?:this|that|it)(?:\s+cost)?\??",
        cleaned_issue.strip(),
    ))
    asks_total_cost = any(phrase in cleaned_issue for phrase in (
        "total cost", "total price", "cost of", "price of",
        "how much is", "how much will", "what will it cost",
    )) or bool(_re.search(
        r"\b(?:how much\b.{0,30}\b(?:flat|unit|home)\b|(?:flat|unit|home)\b.{0,12}\b(?:cost|price))",
        cleaned_issue,
    ))
    if not (explicitly_refers_to_flat or bare_reference) or not asks_total_cost:
        return None

    messages = list(conversation_messages or [])
    flat_number = ""
    for message in reversed(messages):
        text = normalize_ai_text(message.get("text", ""))
        match = _re.search(r"\bflat\s*[:#-]?\s*(\d+[a-z0-9-]*)\b", text, flags=_re.IGNORECASE)
        if match:
            flat_number = match.group(1)
            break

    for message in reversed(messages):
        if normalize_ai_text(message.get("sender", "")).lower() not in {"bot", "assistant", "agent"}:
            continue
        text = normalize_ai_text(message.get("text", ""))
        if flat_number and not _re.search(
            rf"\bflat\s*[:#-]?\s*{_re.escape(flat_number)}\b",
            text,
            flags=_re.IGNORECASE,
        ):
            continue
        area_match = _re.search(
            r"saleable\s+area\s*:\s*([\d,.]+)\s*(?:sq\.?\s*ft|sqft)",
            text,
            flags=_re.IGNORECASE,
        )
        rate_match = _re.search(
            r"(?:live|base)?\s*(?:price|rate)\s*:\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)\s*(?:-|–|to)\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)",
            text,
            flags=_re.IGNORECASE,
        )
        if not area_match or not rate_match:
            continue
        area = _parse_number(area_match.group(1))
        minimum_rate = _parse_number(rate_match.group(1))
        maximum_rate = _parse_number(rate_match.group(2))
        if not area or not minimum_rate or not maximum_rate:
            continue

        label = f"Flat {flat_number}" if flat_number else "This flat"
        minimum_amount = area * minimum_rate
        maximum_amount = area * maximum_rate
        return (
            f"For {label}, the estimated base cost is {_format_inr(minimum_amount)} to "
            f"{_format_inr(maximum_amount)} ({area:g} sq. ft. × {_format_inr(minimum_rate)}–"
            f"{_format_inr(maximum_rate)} per sq. ft.).\n\n"
            "This is a base-price estimate, not the final all-inclusive total. Taxes, registration, "
            "floor-rise, parking, maintenance, and other charges may apply; please request the current "
            "cost sheet for the final amount."
        )
    return None


def _build_contextual_same_price_floor_answer(cleaned_issue, matched_chunks, conversation_messages):
    asks_same_price = any(phrase in cleaned_issue for phrase in (
        "same price", "same cost", "same rate", "similar price", "similar cost",
    ))
    floor_match = _re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+floor\b", cleaned_issue)
    if not asks_same_price or not floor_match:
        return None

    target_floor = int(floor_match.group(1))
    messages = list(conversation_messages or [])
    reference_text = ""
    for message in reversed(messages):
        text = normalize_ai_text(message.get("text", ""))
        if (
            _re.search(r"\bflat\s*[:#-]?\s*\d+", text, flags=_re.IGNORECASE)
            and "saleable area" in text.lower()
            and _re.search(r"(?:live|base)?\s*(?:price|rate)\s*:", text, flags=_re.IGNORECASE)
        ):
            reference_text = text
            break
    if not reference_text:
        return None

    flat_match = _re.search(r"\bflat\s*[:#-]?\s*(\d+[a-z0-9-]*)\b", reference_text, flags=_re.IGNORECASE)
    area_match = _re.search(r"saleable\s+area\s*:\s*([\d,.]+)", reference_text, flags=_re.IGNORECASE)
    rate_match = _re.search(
        r"(?:live|base)?\s*(?:price|rate)\s*:\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)\s*(?:-|–|to)\s*(?:inr|rs\.?|₹)?\s*([\d,.]+)",
        reference_text,
        flags=_re.IGNORECASE,
    )
    type_match = _re.search(r"\b([1-5]\s*BHK(?:\+T)?)\b", reference_text, flags=_re.IGNORECASE)
    if not flat_match or not area_match or not rate_match:
        return None

    reference_flat = flat_match.group(1)
    reference_area = _parse_number(area_match.group(1))
    minimum_rate = _parse_number(rate_match.group(1))
    maximum_rate = _parse_number(rate_match.group(2))
    reference_type = _re.sub(r"\s+", "", type_match.group(1)).lower() if type_match else ""
    if not reference_area or not minimum_rate or not maximum_rate:
        return None

    history_text = " ".join(normalize_ai_text(message.get("text", "")) for message in messages)
    project_chunks = [
        chunk for chunk in (matched_chunks or [])
        if normalize_ai_text(chunk.get("project_name", "")) and chunk.get("inventory_loaded")
    ]
    selected_project = next(
        (chunk for chunk in reversed(project_chunks) if normalize_ai_text(chunk.get("project_name", "")).lower() in history_text.lower()),
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
        unit_type = _re.sub(r"\s+", "", normalize_ai_text(unit.get("typologyType", ""))).lower()
        if unit_floor != target_floor or unit_area != reference_area:
            continue
        if reference_type and unit_type and unit_type != reference_type:
            continue
        matches.append(unit)

    project_name = normalize_ai_text(selected_project.get("project_name", "the selected project"))
    if not matches:
        return (
            f"No currently available flat on floor {target_floor} in {project_name} matches Flat {reference_flat}'s "
            f"configuration and {reference_area:g} sq. ft. saleable area at the same listed rate. "
            "I can check the closest available size or price on that floor instead."
        )

    unit_labels = list(dict.fromkeys(str(unit.get("unitNumber") or unit.get("id")) for unit in matches))
    minimum_amount = reference_area * minimum_rate
    maximum_amount = reference_area * maximum_rate
    return (
        f"Yes. On floor {target_floor} in {project_name}, the matching available "
        f"flat{'s are' if len(unit_labels) != 1 else ' is'} {', '.join('Flat ' + label for label in unit_labels)}. "
        f"{'They have' if len(unit_labels) != 1 else 'It has'} the same {reference_area:g} sq. ft. saleable area "
        f"and listed rate of {_format_inr(minimum_rate)}–{_format_inr(maximum_rate)} per sq. ft., giving the same "
        f"estimated base-cost range of {_format_inr(minimum_amount)}–{_format_inr(maximum_amount)}. "
        "Availability and the final cost sheet should be confirmed before booking."
    )

def _project_catalogue_from_chunks(matched_chunks):
    catalogue = next((chunk for chunk in (matched_chunks or []) if normalize_ai_text(chunk.get("source_key", "")) == "acrobuild-cs-projects"), {})
    projects = catalogue.get("projects", []) or []
    names = [normalize_ai_text(name) for name in catalogue.get("project_names", []) if normalize_ai_text(name)]
    if not names:
        names = [normalize_ai_text(project.get("projectName", "")) for project in projects if normalize_ai_text(project.get("projectName", ""))]
    return catalogue, projects, list(dict.fromkeys(names))

def _is_project_catalogue_question(cleaned_issue):
    if "project" not in cleaned_issue:
        return False
    comparison_or_detail_terms = (
        "bhk", "cheapest", "cost", "fewest", "flat", "floor", "highest",
        "home", "location", "lowest", "most", "price", "pricing", "rate",
        "shop", "shops", "commercial", "thane", "unit", "wing",
    )
    if any(term in cleaned_issue for term in comparison_or_detail_terms):
        return False
    asks_to_fetch_catalogue = bool(_re.search(
        r"\b(?:fetch|get|give|load|list|show)\b.*\bprojects?\b",
        cleaned_issue,
    ))
    asks_which_projects_exist = bool(_re.search(
        r"\bprojects?\s+(?:(?:do|does)\s+)?(?:you|u|acrobuild)\s+have\b",
        cleaned_issue,
    ))
    return (
        "existing projects" in cleaned_issue
        or "list projects" in cleaned_issue
        or "show projects" in cleaned_issue
        or "projects do you have" in cleaned_issue
        or "your projects" in cleaned_issue
        or asks_to_fetch_catalogue
        or asks_which_projects_exist
        or (
            ("tell me about the projects" in cleaned_issue or "tell me about projects" in cleaned_issue)
            and " of " not in cleaned_issue
            and " for " not in cleaned_issue
        )
    )


def _is_project_count_question(cleaned_issue):
    words = set(_re.findall(r"[a-z0-9]+", cleaned_issue))
    return (
        bool(words.intersection({"project", "projects"}))
        and bool(words.intersection({"many", "count", "number", "total"}))
        and not bool(words.intersection({
            "bhk", "flat", "flats", "home", "homes", "shop", "shops", "unit", "units",
            "wing", "wings", "floor", "floors",
        }))
    )


def _build_project_count_answer(matched_chunks):
    catalogue, projects, names = _project_catalogue_from_chunks(matched_chunks)
    count = catalogue.get("record_count") if isinstance(catalogue.get("record_count"), int) else len(projects or names)
    if not count:
        return "The live CS API returned no available projects."
    return f"There are currently {count} projects available in the live Acrobuild CS API."


def _is_portfolio_overview_question(cleaned_issue):
    has_all_project_scope = any(phrase in cleaned_issue for phrase in (
        "all projects", "all of your projects", "all your projects", "each project",
        "every project", "entire portfolio", "project portfolio",
    ))
    asks_explanation = any(term in cleaned_issue for term in (
        "overview", "overviews", "explain", "summary", "summarize", "details", "about",
    ))
    return has_all_project_scope and asks_explanation


def _build_portfolio_overview_answer(matched_chunks):
    project_chunks = [
        chunk for chunk in (matched_chunks or [])
        if normalize_ai_text(chunk.get("project_name", ""))
    ]
    if not project_chunks:
        return "I could not retrieve the project portfolio details right now. Please try again shortly."

    lines = [f"Here is a verified overview of all {len(project_chunks)} Acrobuild projects:"]
    for index, chunk in enumerate(project_chunks, start=1):
        project = chunk.get("project", {}) or {}
        name = normalize_ai_text(chunk.get("project_name", "Project"))
        location_candidates = [
            normalize_ai_text(project.get(key, ""))
            for key in ("location", "address", "city")
        ]
        location = next((value for value in location_candidates if value and "@" not in value), "")
        rera = normalize_ai_text(project.get("reraNo", ""))
        wings = chunk.get("wings", []) or []
        typologies = chunk.get("typologies", []) or []
        home_types = []
        for item in typologies:
            value = normalize_ai_text(item.get("typologyType", "")).strip()
            if not _re.fullmatch(r"(?:[1-5]\s*(?:bhk|rk)(?:\+t)?(?:\s+duplex)?|shop\d*)", value, flags=_re.IGNORECASE):
                continue
            normalized_value = _re.sub(r"\s+", "", value) if "duplex" not in value.lower() else value
            if normalized_value not in home_types:
                home_types.append(normalized_value)
        floor_values = [wing.get("totalFloors") for wing in wings if wing.get("totalFloors") not in (None, "")]

        lines.extend(["", f"{index}. {name}"])
        if location:
            lines.append(f"- Location: {location}")
        if rera:
            lines.append(f"- RERA: {rera}")
        if wings:
            floor_summary = f"; floors: {', '.join(str(value) for value in floor_values)}" if floor_values else ""
            lines.append(f"- Wings: {len(wings)}{floor_summary}")
        if home_types:
            lines.append(f"- Configurations: {', '.join(home_types)}")

    lines.extend(["", "Tell me a project name if you want live availability, pricing, or a deeper wing-level explanation."])
    return "\n".join(lines)

def _build_project_catalogue_answer(matched_chunks):
    _, _, names = _project_catalogue_from_chunks(matched_chunks)
    if not names:
        return "I could not retrieve the project catalogue right now. Please try again shortly."
    return "\n".join([f"We currently have {len(names)} projects in the retrieved Acrobuild catalogue:", "", *[f"{index}. {name}" for index, name in enumerate(names, start=1)], "", "Tell me a project name and what you want to know: overview, location, configurations, pricing, availability, or site visit."])

def _build_acrobuild_overview(matched_chunks):
    company_chunk = next((chunk for chunk in (matched_chunks or []) if normalize_ai_text(chunk.get("source_key", "")) == "acrobuild-cs-company"), {})
    company = company_chunk.get("company", {}) or {}
    _, _, project_names = _project_catalogue_from_chunks(matched_chunks)
    company_name = normalize_ai_text(company.get("businessName") or company.get("companyName") or "GBK Group")
    lines = [f"Acrobuild Support is the property-information and customer-support assistant for {company_name}.", "", "I can provide verified project overviews, locations, wings, floors, home configurations, live availability, API-listed pricing, and site-visit support."]
    if project_names:
        lines.extend(["", f"The current retrieved catalogue contains {len(project_names)} projects."])
    office = normalize_ai_text(company.get("address", ""))
    website = normalize_ai_text(company.get("websiteUrl", ""))
    if office:
        lines.extend(["", f"Office: {office}."])
    if website:
        lines.append(f"Website: {website}.")
    return "\n".join(lines)


def _is_vague_project_recommendation(cleaned_issue):
    asks_recommendation = (
        "project" in cleaned_issue
        and any(term in cleaned_issue for term in (
            "best", "recommend", "suggest", "should i choose", "which one should i choose",
        ))
    )
    decision_criteria = (
        "bhk", "rk", "shop", "budget", "lakh", "crore", "price", "affordable",
        "cheap", "premium", "location", "ambernath", "kalyan", "thane", "mumbai",
        "ready", "possession", "construction", "floor", "wing", "largest", "smallest",
        "investment", "family", "rental", "amenit", "school", "hospital", "station",
    )
    return asks_recommendation and not any(term in cleaned_issue for term in decision_criteria)


def _build_project_recommendation_clarification():
    return (
        "I can recommend the best-matching project for you, but there is no single best project for everyone. "
        "Please share your budget, preferred configuration (for example 1 BHK, 2 BHK, or shop), "
        "preferred location, possession preference (ready or under construction), and what matters most "
        "to you: price, space, amenities, commute, or investment potential."
    )


def _is_budget_project_recommendation(cleaned_issue):
    return (
        "project" in cleaned_issue
        and any(term in cleaned_issue for term in ("recommend", "suggest", "best"))
        and any(term in cleaned_issue for term in ("budget", "affordable", "low cost", "low-cost", "cheapest"))
        and not any(term in cleaned_issue for term in ("bhk", "flat", "home", "apartment", "unit", "shop"))
    )


def _requested_bhk_types(cleaned_issue):
    return list(dict.fromkeys(
        f"{value}BHK"
        for value in _re.findall(r"\b([1-5])\s*bhk\b", cleaned_issue, flags=_re.IGNORECASE)
    ))


def _is_multi_bhk_budget_recommendation(cleaned_issue):
    return (
        len(_requested_bhk_types(cleaned_issue)) > 1
        and any(term in cleaned_issue for term in (
            "budget", "affordable", "low cost", "low-cost", "cheapest", "friendly",
        ))
        and any(term in cleaned_issue for term in (
            "both", "having", "has both", "project with", "which has",
        ))
    )


def _build_multi_bhk_budget_recommendation(cleaned_issue, matched_chunks):
    requested_types = _requested_bhk_types(cleaned_issue)
    candidates = []
    for chunk in matched_chunks or []:
        project_name = normalize_ai_text(chunk.get("project_name", ""))
        if not project_name or not chunk.get("inventory_loaded"):
            continue
        typologies = {item.get("id"): item for item in (chunk.get("typologies", []) or [])}
        options_by_type = {home_type: [] for home_type in requested_types}
        for unit in chunk.get("available_inventory", []) or []:
            raw_type = normalize_ai_text(unit.get("typologyType") or unit.get("typologyName") or "")
            type_match = _re.search(r"\b([1-5])\s*bhk\b", raw_type, flags=_re.IGNORECASE)
            if not type_match:
                continue
            home_type = f"{type_match.group(1)}BHK"
            if home_type not in options_by_type:
                continue
            typology = typologies.get(unit.get("typologyId"), {}) or {}
            rate = typology.get("minBasePrice")
            area = unit.get("saleableArea") or typology.get("saleableArea")
            if not isinstance(rate, (int, float)) or not isinstance(area, (int, float)) or rate <= 0 or area <= 0:
                continue
            options_by_type[home_type].append({
                "area": float(area), "rate": float(rate),
                "estimated_base": float(rate) * float(area),
            })
        if all(options_by_type.values()):
            cheapest = {key: min(values, key=lambda item: item["estimated_base"]) for key, values in options_by_type.items()}
            candidates.append((sum(item["estimated_base"] for item in cheapest.values()), project_name, cheapest, options_by_type))

    if not candidates:
        requested_label = " and ".join(requested_types)
        return (
            f"I could not find a single project with live, priced availability for both {requested_label} "
            "configurations right now."
        )

    _, project_name, cheapest, options_by_type = min(candidates, key=lambda item: item[0])
    lines = [
        f"{project_name} is the most budget-friendly project I found with live availability for both "
        f"{' and '.join(requested_types)}:",
    ]
    for home_type in requested_types:
        entry = cheapest[home_type]
        lines.extend([
            "",
            f"- {home_type}: {entry['area']:g} sq. ft. at INR {entry['rate']:,.0f} per sq. ft.",
            f"  Estimated base amount: INR {entry['estimated_base'] / 100000:.2f} lakh "
            f"({len(options_by_type[home_type])} available unit{'s' if len(options_by_type[home_type]) != 1 else ''})",
        ])
    lines.extend([
        "",
        "These estimates use the API minimum rate multiplied by saleable area. Taxes, registration, "
        "floor-rise, parking, maintenance, and other charges are not included. Availability and rates may change.",
    ])
    return "\n".join(lines)


def _build_recommendation_budget_follow_up(cleaned_issue, conversation_messages):
    asks_affordability = any(phrase in cleaned_issue for phrase in (
        "is it sufficient", "is this sufficient", "is that sufficient",
        "can i buy it", "can i afford it", "is it enough", "will it be enough",
    ))
    budget_match = _re.search(
        r"(?:budget\s*(?:is|of)?\s*)?(?:inr|rs\.?|rupees?)?\s*([\d,.]+)\s*(lakh|lac|crore)",
        cleaned_issue,
    )
    if not asks_affordability or not budget_match:
        return None

    multiplier = 10000000 if budget_match.group(2) == "crore" else 100000
    budget = float(budget_match.group(1).replace(",", "")) * multiplier
    prior_answer = ""
    for message in reversed(conversation_messages or []):
        if normalize_ai_text(message.get("sender", "")).lower() in {"bot", "assistant", "agent"}:
            candidate = normalize_ai_text(message.get("text", ""))
            if "estimated base amount" in candidate.lower():
                prior_answer = candidate
                break
    if not prior_answer:
        return None

    amount_matches = _re.findall(
        r"estimated base amount:\s*inr\s*([\d,.]+)\s*(lakh|lac|crore)?",
        prior_answer,
        flags=_re.IGNORECASE,
    )
    if not amount_matches:
        return None
    estimated_total = 0.0
    for value, unit in amount_matches:
        numeric_value = float(value.replace(",", ""))
        if unit.lower() == "crore":
            numeric_value *= 10000000
        elif unit.lower() in {"lakh", "lac"}:
            numeric_value *= 100000
        estimated_total += numeric_value

    project_match = _re.search(
        r"^(.+?) is the most budget-friendly project",
        prior_answer,
        flags=_re.IGNORECASE,
    )
    project_name = project_match.group(1).strip() if project_match else "the recommended project"
    difference = budget - estimated_total
    if difference >= 0:
        conclusion = (
            f"Yes. A budget of INR {budget / 100000:.2f} lakh covers the estimated combined base amount "
            f"of INR {estimated_total / 100000:.2f} lakh for the recommended 1BHK and 2BHK in {project_name}. "
            f"That leaves about INR {difference / 100000:.2f} lakh before additional charges."
        )
    else:
        conclusion = (
            f"No. The estimated combined base amount for the recommended 1BHK and 2BHK in {project_name} "
            f"is INR {estimated_total / 100000:.2f} lakh, which exceeds your INR {budget / 100000:.2f} lakh "
            f"budget by about INR {-difference / 100000:.2f} lakh."
        )
    return (
        conclusion
        + "\n\nThis comparison covers base amounts only. Taxes, registration, floor-rise, parking, maintenance, "
        "and other charges must also fit within your budget, so the final quotation needs to be checked."
    )


def _build_budget_project_recommendation(matched_chunks):
    options = []
    for chunk in matched_chunks or []:
        project_name = normalize_ai_text(chunk.get("project_name", ""))
        if not project_name or not chunk.get("inventory_loaded"):
            continue
        typologies = {item.get("id"): item for item in (chunk.get("typologies", []) or [])}
        for unit in chunk.get("available_inventory", []) or []:
            home_type = normalize_ai_text(unit.get("typologyType") or unit.get("typologyName") or "")
            if not home_type or "shop" in home_type.lower() or "commercial" in home_type.lower():
                continue
            typology = typologies.get(unit.get("typologyId"), {}) or {}
            rate = typology.get("minBasePrice")
            area = unit.get("saleableArea") or typology.get("saleableArea")
            if not isinstance(rate, (int, float)) or not isinstance(area, (int, float)) or rate <= 0 or area <= 0:
                continue
            options.append({
                "project": project_name,
                "home_type": home_type.strip(),
                "area": float(area),
                "rate": float(rate),
                "estimated_base": float(rate) * float(area),
            })
    if not options:
        return (
            "I could not calculate a grounded budget-friendly recommendation because live residential "
            "availability and comparable API pricing are not available right now."
        )

    options.sort(key=lambda item: item["estimated_base"])
    entry = options[0]
    one_bhk_options = [item for item in options if "1bhk" in item["home_type"].replace(" ", "").lower()]
    lowest_one_bhk = one_bhk_options[0] if one_bhk_options else None

    def amount_lakh(value):
        return f"INR {value / 100000:.2f} lakh"

    lines = [
        f"Based on the lowest estimated base price among currently available residential units, "
        f"{entry['project']} is the most budget-friendly entry option right now:",
        "",
        f"- Configuration: {entry['home_type']}",
        f"- Saleable area: {entry['area']:g} sq. ft.",
        f"- API minimum rate: INR {entry['rate']:,.0f} per sq. ft.",
        f"- Estimated base amount: {amount_lakh(entry['estimated_base'])}",
    ]
    if lowest_one_bhk and lowest_one_bhk["project"] != entry["project"]:
        lines.extend([
            "",
            f"If you specifically want a 1 BHK, {lowest_one_bhk['project']} currently has the lowest "
            f"entry estimate at {amount_lakh(lowest_one_bhk['estimated_base'])} "
            f"({lowest_one_bhk['area']:g} sq. ft. at INR {lowest_one_bhk['rate']:,.0f} per sq. ft.).",
        ])
    lines.extend([
        "",
        "This is an estimate using minimum API rate multiplied by saleable area. Taxes, registration, "
        "floor-rise, parking, maintenance, and other charges are not included. Availability and rates may change.",
        "Tell me your preferred configuration and maximum budget for a like-for-like recommendation.",
    ])
    return "\n".join(lines)


def _is_shop_availability_question(cleaned_issue):
    words = set(_re.findall(r"[a-z0-9]+", cleaned_issue))
    mentions_shop = (
        any(word.startswith("shop") for word in words)
        or bool(words.intersection({"store", "stores", "commercial"}))
    )
    return (
        mentions_shop
        and any(term in cleaned_issue for term in ("available", "availability", "how many", "number of", "total", "count"))
    )


def _build_shop_availability_answer(matched_chunks):
    project_chunks = [
        chunk for chunk in (matched_chunks or [])
        if normalize_ai_text(chunk.get("project_name", ""))
    ]
    loaded_chunks = [chunk for chunk in project_chunks if chunk.get("inventory_loaded")]
    if not loaded_chunks:
        return "I could not load live shop inventory right now. Please try again shortly."

    total = 0
    breakdown = []
    seen_units = set()
    for chunk in loaded_chunks:
        project_name = normalize_ai_text(chunk.get("project_name", "Project"))
        project_count = 0
        for unit in chunk.get("available_inventory", []) or []:
            searchable = " ".join(
                normalize_ai_text(unit.get(key, ""))
                for key in ("typologyName", "typologyType", "unitType", "configuration")
            ).lower()
            if "shop" not in searchable and "commercial" not in searchable:
                continue
            unit_key = (
                chunk.get("project", {}).get("id"), unit.get("wingId"),
                unit.get("id"), unit.get("unitNumber"), unit.get("floorNumber"),
            )
            if unit_key in seen_units:
                continue
            seen_units.add(unit_key)
            project_count += 1
        if project_count:
            total += project_count
            breakdown.append((project_name, project_count))

    lines = [
        f"There are currently {total} available shop unit{'s' if total != 1 else ''} across all {len(loaded_chunks)} projects checked.",
    ]
    if breakdown:
        lines.extend(["", "Available shops by project:"])
        lines.extend(
            f"- {project_name}: {count} available shop unit{'s' if count != 1 else ''}"
            for project_name, count in breakdown
        )
    else:
        lines.extend(["", "No available shop units are currently listed in the live inventory."])
    lines.extend(["", "Availability is live and may change."])
    return "\n".join(lines)

def _find_requested_project(cleaned_issue, matched_chunks):
    project_chunks = [chunk for chunk in (matched_chunks or []) if normalize_ai_text(chunk.get("source_key", "")).startswith("acrobuild-cs-project-") and normalize_ai_text(chunk.get("project_name", ""))]
    project_records = [{"projectName": normalize_ai_text(chunk.get("project_name", "")), "chunk": chunk} for chunk in project_chunks]
    resolved = resolve_project_from_text(project_records, cleaned_issue)
    if resolved:
        return resolved["chunk"]
    ignored = {"about", "deep", "details", "dive", "for", "give", "group", "into", "me", "of", "project", "projects", "the"}
    tokens = {token for token in _re.findall(r"[a-z0-9]+", cleaned_issue) if len(token) >= 3 and token not in ignored}
    matches = [chunk for chunk in project_chunks if tokens.intersection(_re.findall(r"[a-z0-9]+", normalize_ai_text(chunk.get("project_name", "")).lower()))]
    return matches[0] if len(matches) == 1 else None

def _sanitize_project_location_answer(answer, project_chunk):
    if not answer or not project_chunk:
        return answer
    project = project_chunk.get("project", {}) or {}
    values = []
    for key in ("address", "locality", "city"):
        value = normalize_ai_text(project.get(key, ""))
        if value and "@" not in value and not _re.fullmatch(r"\+?\d[\d\s-]{6,}", value):
            values.append(value)
    values = list(dict.fromkeys(values))
    if not values:
        return _re.sub(r"\n\nLocation:[^\n]+", "", answer)
    return _re.sub(r"\n\nLocation:[^\n]+", f"\n\nLocation: {', '.join(values)}.", answer)

def build_company_api_direct_answer(issue, matched_chunks, conversation_messages=None):
    cleaned_issue = normalize_ai_text(issue).lower()
    contextual_flat_cost = _build_contextual_flat_cost_answer(cleaned_issue, conversation_messages)
    if contextual_flat_cost:
        return contextual_flat_cost
    contextual_floor_price = _build_contextual_same_price_floor_answer(
        cleaned_issue, matched_chunks, conversation_messages,
    )
    if contextual_floor_price:
        return contextual_floor_price
    if _is_project_count_question(cleaned_issue):
        return _build_project_count_answer(matched_chunks)
    budget_follow_up = _build_recommendation_budget_follow_up(cleaned_issue, conversation_messages)
    if budget_follow_up:
        return budget_follow_up
    if _is_multi_bhk_budget_recommendation(cleaned_issue):
        return _build_multi_bhk_budget_recommendation(cleaned_issue, matched_chunks)
    if _is_budget_project_recommendation(cleaned_issue):
        return _build_budget_project_recommendation(matched_chunks)
    if _is_vague_project_recommendation(cleaned_issue):
        return _build_project_recommendation_clarification()
    if _is_shop_availability_question(cleaned_issue):
        return _build_shop_availability_answer(matched_chunks)
    if _is_portfolio_overview_question(cleaned_issue):
        return _build_portfolio_overview_answer(matched_chunks)
    if _is_project_catalogue_question(cleaned_issue):
        return _build_project_catalogue_answer(matched_chunks)
    if "acrobuild" in cleaned_issue and any(phrase in cleaned_issue for phrase in ("about acrobuild", "what is acrobuild", "who is acrobuild", "acrobuild company")):
        return _build_acrobuild_overview(matched_chunks)
    requested_project = _find_requested_project(cleaned_issue, matched_chunks)
    asks_project_overview = requested_project is not None and any(phrase in cleaned_issue for phrase in ("about", "overview", "details", "deep dive", "project of", "projects of"))
    effective_issue = f"Tell me more about project {normalize_ai_text(requested_project.get('project_name', ''))}" if asks_project_overview else issue
    answer = _legacy_build_company_api_direct_answer(effective_issue, matched_chunks, conversation_messages=conversation_messages)
    return _sanitize_project_location_answer(answer, requested_project)
