"""Grounded project configuration answers, including absent requested types."""
import re

from services.acrobuild_company_service import (
    build_project_record_index, customer_facing_projects, filter_project_index,
    get_company_projects, get_project_typologies, get_project_wings,
    get_wing_inventory, resolve_project_candidates_from_text,
)
from services.conversation_store_service import get_current_project_context, latest_home_type_scope
from services.property_clarification_service import (
    apply_clarification_contract, build_home_type_scope_clarification,
)


def requested_home_types(text):
    # "s?" -- a plural mention ("3bhks", "2 bhks") names the type just as
    # specifically as the singular form; without it "which one of these has
    # 3bhks?" found no number at all and fell through to the generic (or
    # unrelated) path instead of the catalogue filter.
    return list(dict.fromkeys(re.findall(r"\b([1-6])\s*b(?:h)?ks?\b", str(text), re.I)))


_HOME_TYPE_TERMS_RE = re.compile(r"\bbhks?\b|\bhome\s*types?\b|\bconfigurations?\b", re.I)
_AVAILABILITY_CUE_RE = re.compile(r"\b(?:available|options?|have|are\s+there|offered|offer|exist)\b", re.I)
_COMPLETE_DETAIL_RE = re.compile(
    r"\b(?:all|every|each|full|complete|detailed)\b.{0,35}\b(?:details?|plans?|options?|sizes?|breakdown|typologies)\b"
    r"|\b(?:details?|breakdown)\b",
    re.I,
)
_CONTEXTUAL_COMPLETE_DETAIL_RE = re.compile(
    r"^\s*(?:(?:show|list|give|share)(?:\s+me)?\s+(?:all|every|each)\s+(?:the\s+)?"
    r"(?:details?|plans?|options?|sizes?)|(?:show|give|share)(?:\s+me)?\s+(?:the\s+)?"
    r"(?:full|complete)\s+(?:details?|breakdown)|(?:full|complete)\s+(?:details?|breakdown))\s*[?.!]*\s*$",
    re.I,
)
_SELECTED_PROJECT_RE = re.compile(r"\bselected\s+project\s*:", re.I)
_EXPLICIT_PROJECT_SCOPE_RE = re.compile(r"\b(?:selected|requested)\s+project\s*:", re.I)
_SUBTYPE_RE = re.compile(r"\bduplex(?:es)?\b", re.I)
_PRICE_CUE_RE = re.compile(r"\b(?:price|pricing|cost|rate)\b|\bhow\s+much\b", re.I)
_DIRECT_PLAN_LIMIT = 4


def is_generic_home_type_query(text):
    """A home-type question with no specific BHK number ("what bhks are
    available", "which home types do you have") -- the numbered builders
    below never match this, so without this detector it fell through to the
    general pipeline, which could ask "which project?" again even when the
    project was already unambiguous from context."""
    cleaned = str(text or "")
    if requested_home_types(cleaned):
        return False
    if re.search(r"\b(?:which|all|other|any|different)\s+projects?\b|\bacross\b", cleaned, re.I):
        return False
    return bool(_HOME_TYPE_TERMS_RE.search(cleaned) and _AVAILABILITY_CUE_RE.search(cleaned))


def wants_complete_home_type_details(text):
    """Whether the customer explicitly asked for the full plan breakdown."""
    return bool(_COMPLETE_DETAIL_RE.search(str(text or "")))


def _message_value(message, key):
    return message.get(key) if isinstance(message, dict) else getattr(message, key, None)


def requested_home_subtype(text):
    """Supported subtype explicitly named by the customer or normalized turn."""
    return "duplex" if _SUBTYPE_RE.search(str(text or "")) else ""


def _conversation_home_scope(history):
    messages = list(history or [])
    project = ""
    for message in reversed(messages):
        if str(_message_value(message, "sender") or "").lower() != "bot":
            continue
        project = str((get_current_project_context(_message_value(message, "text")) or {}).get("project") or "").strip()
        if project:
            break
    scope = latest_home_type_scope(messages)
    if scope and scope.get("project") == project:
        return project, list(scope.get("config") or []), str(scope.get("subtype") or "")
    types = []
    for message in reversed(messages):
        if str(_message_value(message, "sender") or "").lower() == "customer":
            types = requested_home_types(_message_value(message, "text"))
            if types:
                break
    return project, types, ""


def _contextual_home_type_issue(issue, history):
    """Restore trusted BHK/project/subtype scope for short grounded follow-ups.

    BHK scope comes from prior customer text and project scope from the
    server-only markers; translated assistant prose is not parsed for intent.
    """
    cleaned = str(issue or "")
    is_details = bool(_CONTEXTUAL_COMPLETE_DETAIL_RE.fullmatch(cleaned))
    explicit_subtype = requested_home_subtype(cleaned)
    is_price = bool(_PRICE_CUE_RE.search(cleaned))
    if not (is_details or explicit_subtype or is_price):
        return issue
    project, prior_types, prior_subtype = _conversation_home_scope(history)
    types = requested_home_types(cleaned) or prior_types
    if not project or _EXPLICIT_PROJECT_SCOPE_RE.search(cleaned):
        return issue
    explicit_projects = resolve_project_candidates_from_text(
        customer_facing_projects(get_company_projects()), cleaned,
    )
    if explicit_projects:
        return issue
    if not types and not explicit_subtype:
        return issue
    subtype = explicit_subtype or (prior_subtype if is_details or is_price else "")
    phrase = " and ".join(f"{number}BHK" for number in types)
    additions = []
    if phrase and not requested_home_types(cleaned):
        additions.append(f"Requested home types: {phrase}")
    if subtype and not requested_home_subtype(cleaned):
        additions.append(f"Requested subtype: {subtype.title()}")
    additions.append(f"Selected project: {project}")
    return f"{issue}. " + ". ".join(additions)


def _contextual_detail_issue(issue, history):
    """Backward-compatible name for the expanded contextual resolver."""
    return _contextual_home_type_issue(issue, history)


def _clean_text(value):
    return " ".join(str(value or "").split())


def _signature_value(value):
    return None if value is None else _clean_text(value).casefold()


def _format_number(value):
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _clean_text(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _value_range(values):
    numeric = []
    for value in values:
        if value is None:
            continue
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            return ""
    if not numeric:
        return ""
    low, high = min(numeric), max(numeric)
    return _format_number(low) if low == high else f"{_format_number(low)} to {_format_number(high)}"


def _plan_groups(records, wings, available_units):
    """Group equal structured facts while retaining labels, wings, and IDs."""
    wing_names = {
        str(wing.get("id")): _clean_text(wing.get("name") or wing.get("code"))
        for wing in wings if wing.get("id") is not None
    }
    groups = {}
    for record in records:
        configuration = _clean_text(record.get("typologyType") or record.get("typologyName"))
        signature = (
            configuration.casefold(),
            _signature_value(record.get("carpetArea")),
            _signature_value(record.get("saleableArea")),
            _signature_value(record.get("rateType")),
            _signature_value(record.get("minBasePrice")),
            _signature_value(record.get("maxBasePrice")),
        )
        group = groups.setdefault(signature, {
            "configuration": configuration,
            "carpetArea": record.get("carpetArea"),
            "saleableArea": record.get("saleableArea"),
            "rateType": record.get("rateType"),
            "minBasePrice": record.get("minBasePrice"),
            "maxBasePrice": record.get("maxBasePrice"),
            "labels": [], "typology_ids": [], "wings": [],
        })
        label = _clean_text(record.get("typologyName"))
        if label and label not in group["labels"]:
            group["labels"].append(label)
        if record.get("id") is not None:
            group["typology_ids"].append(str(record["id"]))
        wing = wing_names.get(str(record.get("wingId")), "")
        if wing and wing not in group["wings"]:
            group["wings"].append(wing)

    for group in groups.values():
        ids = set(group["typology_ids"])
        group["available_units"] = sum(
            1 for unit in available_units if str(unit.get("typologyId")) in ids
        )
    return list(groups.values())


def _rate_detail(group):
    minimum = group.get("minBasePrice")
    if minimum is None:
        return "pricing is not listed"
    maximum = group.get("maxBasePrice") if group.get("maxBasePrice") is not None else minimum
    basis = _clean_text(group.get("rateType")) or "rate basis not listed"
    return f"API-listed base rate: INR {_format_number(minimum)} to INR {_format_number(maximum)} ({basis})"


def _plan_detail(group):
    details = [group["configuration"] or "Configuration name not listed"]
    if group["wings"]:
        details.append("wing" + ("s" if len(group["wings"]) != 1 else "") + ": " + ", ".join(group["wings"]))
    for key, label in (("carpetArea", "carpet area"), ("saleableArea", "saleable area")):
        if group.get(key) is not None:
            details.append(f"{label}: {_format_number(group[key])} sq. ft.")
    details.append(_rate_detail(group))
    details.append(f"{group['available_units']} available unit(s) linked to this variant")
    labels = group["labels"]
    if labels and (len(labels) > 1 or labels[0].casefold() != group["configuration"].casefold()):
        details.append(("source labels: " if len(labels) > 1 else "source label: ") + " / ".join(labels))
    return "; ".join(details)


def _configuration_summaries(groups):
    buckets = {}
    for group in groups:
        key = group["configuration"].casefold()
        buckets.setdefault(key, {"name": group["configuration"], "groups": []})["groups"].append(group)
    lines = []
    for bucket in buckets.values():
        variants = bucket["groups"]
        details = [f"{bucket['name']}: {len(variants)} distinct area/rate variant(s)"]
        carpet = _value_range([item.get("carpetArea") for item in variants])
        saleable = _value_range([item.get("saleableArea") for item in variants])
        if carpet:
            qualifier = " where listed" if any(item.get("carpetArea") is None for item in variants) else ""
            details.append(f"carpet area {carpet} sq. ft.{qualifier}")
        if saleable:
            qualifier = " where listed" if any(item.get("saleableArea") is None for item in variants) else ""
            details.append(f"saleable area {saleable} sq. ft.{qualifier}")
        bases = {_clean_text(item.get("rateType")).casefold() for item in variants}
        rates_complete = all(item.get("minBasePrice") is not None for item in variants)
        if len(bases) == 1 and rates_complete:
            minimums = [item.get("minBasePrice") for item in variants]
            maximums = [item.get("maxBasePrice") if item.get("maxBasePrice") is not None else item.get("minBasePrice")
                        for item in variants]
            try:
                rate_range = f"{_format_number(min(float(value) for value in minimums))} to " \
                             f"{_format_number(max(float(value) for value in maximums))}"
            except (TypeError, ValueError):
                details.append("base-rate details vary by plan")
            else:
                basis = _clean_text(variants[0].get("rateType")) or "rate basis not listed"
                details.append(f"API-listed base rate INR {rate_range} ({basis})")
        else:
            details.append("base-rate details vary by plan")
        lines.append("  - " + "; ".join(details))
    return lines


def build_generic_home_type_answer(issue, history=None):
    """Resolve a numberless BHK/home-type question through the shared
    clarification contract, so a project already known from context resolves
    straight to a wing choice (or the answer) instead of re-asking for the
    project."""
    if not is_generic_home_type_query(issue):
        return None
    return apply_clarification_contract({"clarification_entity": "home_type"}, issue, history)


def is_catalogue_home_type_query(text):
    """A home-type filter over projects, rather than one selected project."""
    cleaned = str(text or "")
    if _SELECTED_PROJECT_RE.search(cleaned):
        return False
    # "which one of these has 3bhks", "any of these", "out of these" refer
    # back to a set of projects (the catalogue, or an already-offered
    # shortlist) without ever saying "project(s)".
    plural_scope = re.search(
        r"\b(?:projects|properties|developments)\b|\bof\s+(?:these|them|those)\b", cleaned, re.I,
    )
    singular_filter = re.search(r"\b(?:which|what)\s+(?:project|property)\b", cleaned, re.I)
    filter_cue = re.search(
        r"\b(?:which|what|list|show|find|any|all|where)\b|\bdo\s+you\s+have\b",
        cleaned, re.I,
    )
    return bool(requested_home_types(cleaned) and (singular_filter or (plural_scope and filter_cue)))


def _record_matches_type(record, number):
    return number in requested_home_types(
        record.get("typologyName") or record.get("typologyType") or ""
    )


def _record_matches_subtype(record, subtype):
    if not subtype:
        return True
    configuration = str(record.get("typologyType") or record.get("typologyName") or "")
    return bool(_SUBTYPE_RE.search(configuration)) if subtype == "duplex" else False


def _subtype_types(records, subtype):
    return list(dict.fromkeys(
        number for record in records if _record_matches_subtype(record, subtype)
        for number in requested_home_types(record.get("typologyType") or record.get("typologyName") or "")
    ))


def _home_type_scope(project, types, subtype=""):
    scope = {"project": str(project.get("projectName") or "").strip(), "config": list(types)}
    if subtype:
        scope["subtype"] = subtype
    return scope


def _project_for_issue(issue, history):
    projects = customer_facing_projects(get_company_projects())
    candidates = resolve_project_candidates_from_text(projects, issue)
    if len(candidates) != 1:
        return None, apply_clarification_contract({"clarification_entity": "project"}, issue, history)
    return candidates[0], None


def _pricing_summary(groups):
    buckets = {}
    for group in groups:
        key = group["configuration"].casefold()
        buckets.setdefault(key, {"name": group["configuration"], "groups": []})["groups"].append(group)
    lines = []
    for bucket in buckets.values():
        variants = bucket["groups"]
        minimums = [group.get("minBasePrice") for group in variants if group.get("minBasePrice") is not None]
        maximums = [group.get("maxBasePrice") if group.get("maxBasePrice") is not None
                    else group.get("minBasePrice") for group in variants if group.get("minBasePrice") is not None]
        bases = {_clean_text(group.get("rateType")) or "rate basis not listed" for group in variants}
        if not minimums:
            rate = "pricing is not listed"
        elif len(bases) != 1:
            rate = "base-rate units vary by plan; ask for all details"
        else:
            rate = (f"API-listed base rate: INR {_format_number(min(float(value) for value in minimums))} "
                    f"to INR {_format_number(max(float(value) for value in maximums))} ({next(iter(bases))})")
        lines.append(f"- {bucket['name']}: {len(variants)} listed plan variant(s); {rate}")
    return lines


def build_project_home_type_price_answer(issue, history=None):
    """Answer price/rate follow-ups within the verified project/BHK/subtype scope."""
    issue = _contextual_home_type_issue(issue, history)
    if not _PRICE_CUE_RE.search(issue):
        return None
    if re.search(r"\b(?:flat|unit|shop|budget|under|below|above|cheapest|highest|lowest|compare|"
                 r"total|final|all[- ]inclusive|tax|stamp|parking|floor\s*rise|cost\s*sheet)\b", issue, re.I):
        return None
    types = requested_home_types(issue)
    subtype = requested_home_subtype(issue)
    if not types and not subtype:
        return None
    project, clarification = _project_for_issue(issue, history)
    if clarification:
        return clarification
    records = get_project_typologies(project["id"])
    if not types and subtype:
        types = _subtype_types(records, subtype)
        if len(types) > 1:
            options = [f"{number}BHK {subtype.title()}" for number in types]
            return build_home_type_scope_clarification(issue, project["projectName"], options)
    matching = [record for record in records
                if any(_record_matches_type(record, number) for number in types)
                and _record_matches_subtype(record, subtype)]
    label = " and ".join(f"{number}BHK" for number in types)
    if subtype:
        label += f" {subtype.title()}"
    groups = _plan_groups(matching, [], [])
    if not groups:
        answer = (
            f"The live project configuration for {project['projectName']} lists no {label} pricing. "
            "I have not substituted another home type."
        )
    elif wants_complete_home_type_details(issue):
        answer = "\n".join([
            f"Complete API-listed base pricing for {label} in {project['projectName']}:",
            *["- " + "; ".join(part for part in (
                group["configuration"] or "Configuration name not listed",
                f"carpet area: {_format_number(group['carpetArea'])} sq. ft." if group.get("carpetArea") is not None else "",
                f"saleable area: {_format_number(group['saleableArea'])} sq. ft." if group.get("saleableArea") is not None else "",
                _rate_detail(group),
            ) if part) for group in groups],
            "These are API-listed base rates, not all-inclusive home quotations.",
        ])
    else:
        answer = "\n".join([
            f"Pricing for {label} in {project['projectName']}:",
            *_pricing_summary(groups),
            "These are API-listed base rates, not all-inclusive home quotations. Ask for all pricing details for the size-by-size breakdown.",
        ])
    established_subtype = subtype if matching else ""
    return {
        "answer": answer, "route": "property", "source_status": "live_api",
        "agent_mode": "knowledge_retrieval", "used_llm": False,
        "confidence_label": "high", "source_label": "AcroBuild project configuration records",
        "retrieval_mode": "live_project_records",
        "home_type_scope": _home_type_scope(project, types, established_subtype),
        "matched_chunks": [{"record_kind": "company_api", "source_key": f"project-{project['id']}-home-type-pricing",
                            "project": project, "typologies": records, "body_text": answer}],
    }


def build_catalogue_home_type_answer(issue):
    """Filter the live project catalogue by every requested BHK type.

    Uses the shared build_project_record_index()/filter_project_index()
    mechanism (services/acrobuild_company_service.py) so one project's live
    (and snapshot-fallback) failure -- e.g. it was added to the catalogue
    after the on-disk snapshot was last regenerated, so it has no fallback
    yet -- skips that project instead of aborting the whole catalogue-wide
    scan. Previously an uncaught RuntimeError from any single project's
    fetch made this and every other "which projects have X?" question
    fall through to the general pipeline, which does not filter reliably.
    """
    if not is_catalogue_home_type_query(issue):
        return None
    types = requested_home_types(issue)
    index, failed = build_project_record_index(
        get_project_typologies, projects=customer_facing_projects(get_company_projects()),
    )
    matches, _per_type = filter_project_index(
        index,
        lambda entry: {number for number in types
                       if any(_record_matches_type(record, number) for record in entry["records"])},
        types,
    )

    phrase = " and ".join(f"{number}BHK" for number in types)
    names = [str(project.get("projectName") or "").strip() for project in matches]
    if names:
        answer = "\n".join([
            f"These projects list {phrase} in their latest configuration data:",
            "",
            *[f"- {name}" for name in names],
            "",
            "Select a project and I’ll check its current details and availability.",
        ])
    else:
        answer = (
            f"None of the projects in the latest catalogue list {phrase}. "
            "This reflects the currently published configuration data."
        )
    if failed:
        skipped_names = ", ".join(
            str(project.get("projectName") or "a project").strip() for project, _error in failed
        )
        answer += (
            f"\n\nNote: {len(failed)} project{'s' if len(failed) != 1 else ''} ({skipped_names}) could not "
            "be checked right now because live data was temporarily unavailable; this result may be incomplete."
        )
    evidence = [{
        "record_kind": "company_api",
        "source_key": f"project-{entry['project']['id']}-home-type-filter",
        "project": entry["project"],
        "typologies": entry["records"],
        "body_text": "\n".join(str(record.get("typologyName") or record.get("typologyType") or "")
                                  for record in entry["records"]),
    } for entry in index.values()]
    payload = {
        "answer": answer, "route": "property", "source_status": "live_api",
        "agent_mode": "knowledge_retrieval", "used_llm": False,
        "confidence_label": "high", "source_label": "AcroBuild project configuration records",
        "retrieval_mode": "live_project_records", "matched_chunks": evidence,
        "catalogue_home_type_search": True,
    }
    if names:
        payload.update({
            "clarification_entity": "project",
            "pending_project_lookup": {
                "kind": "selection", "entity": "project", "options": names,
                "scope": {}, "original_issue": issue, "purpose": "home_type_search",
            },
            "quick_replies": [{"label": name, "value": name} for name in names],
        })
    return payload


def build_project_home_type_answer(issue, history=None):
    issue = _contextual_home_type_issue(issue, history)
    types = requested_home_types(issue)
    subtype = requested_home_subtype(issue)
    if not types and not subtype:
        return None
    selected_project = bool(_SELECTED_PROJECT_RE.search(issue))
    if not selected_project and (is_catalogue_home_type_query(issue) or re.search(r"\b(?:which|all|other|any|different)\s+projects?\b|\bacross\b", issue, re.I)):
        return None
    # More specific unit, comparison and budget requests retain their own builders.
    if re.search(r"\b(?:wing|floor|flat\s*\d|budget|under|below|cheapest|compare|amenities|location|possession|documents)\b", issue, re.I):
        return None
    project, clarification = _project_for_issue(issue, history)
    if clarification:
        return clarification
    typologies = get_project_typologies(project["id"])
    if not types and subtype:
        types = _subtype_types(typologies, subtype)
        if len(types) > 1:
            options = [f"{number}BHK {subtype.title()}" for number in types]
            return build_home_type_scope_clarification(issue, project["projectName"], options)
    wings = get_project_wings(project["id"])
    units = [unit for wing in wings for unit in get_wing_inventory(wing["id"])]
    by_id = {str(t.get("id")): t for t in typologies}
    complete_details = wants_complete_home_type_details(issue)

    def matches(record, number):
        return _record_matches_type(record, number)

    lines = [f"Home types in {project['projectName']}:"]
    any_subtype_match = False
    for number in types:
        records = [t for t in typologies if matches(t, number) and _record_matches_subtype(t, subtype)]
        record_ids = {str(record.get("id")) for record in records if record.get("id") is not None}
        if subtype:
            available = [unit for unit in units if str(unit.get("typologyId")) in record_ids]
        else:
            available = [u for u in units if matches(u, number) or matches(by_id.get(str(u.get('typologyId')), {}), number)]
        label = f"{number}BHK" + (f" {subtype.title()}" if subtype else "")
        if not records and not available:
            if subtype:
                lines.append(
                    f"- The live project configuration lists no {label} option. "
                    f"I have not treated another {number}BHK typology as {subtype.title()}."
                )
            else:
                lines.append(f"- {label}: Not listed in this project's current configuration or available-unit records.")
            continue
        any_subtype_match = any_subtype_match or bool(subtype)
        availability = (f"{len(available)} unit(s) currently listed as available." if available else
                        "This configuration is listed, but no units are currently listed as available.")
        lines.append(f"- {label}: {availability}")
        groups = _plan_groups(records, wings, available)
        if complete_details or len(groups) <= _DIRECT_PLAN_LIMIT:
            lines.extend("  - " + _plan_detail(group) for group in groups)
        else:
            lines.append(f"  {len(groups)} distinct area/rate variants are listed. Here is a concise overview:")
            lines.extend(_configuration_summaries(groups))
            lines.append(f"  Ask me to show all {label} details for the complete size-by-size breakdown.")
        inconsistent = sum(1 for group in groups if len(group["labels"]) > 1)
        if inconsistent:
            lines.append(
                f"  Note: {inconsistent} grouped variant(s) have differing or conflicting source labels; "
                "the structured configuration, area, rate, and wing fields are shown without guessing."
            )
    listed = list(dict.fromkeys(str(t.get("typologyName")) for t in typologies if t.get("typologyName")))
    if not subtype and any(not any(matches(t, number) for t in typologies) for number in types) and listed:
        lines.append("Listed configurations: " + ", ".join(listed) + ".")
    answer = "\n".join(lines)
    return {
        "answer": answer, "route": "property", "source_status": "live_api",
        "agent_mode": "knowledge_retrieval", "used_llm": False,
        "confidence_label": "high", "source_label": "AcroBuild project and inventory records",
        "retrieval_mode": "live_project_records",
        "home_type_scope": _home_type_scope(project, types, subtype if any_subtype_match else ""),
        "matched_chunks": [{"record_kind": "company_api", "source_key": f"project-{project['id']}-home-types",
                            "project": project, "typologies": typologies, "units": units, "body_text": answer}],
    }
