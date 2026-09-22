"""Grounded project configuration answers, including absent requested types."""
import re

from services.acrobuild_company_service import (
    build_project_record_index, customer_facing_projects, filter_project_index,
    get_company_projects, get_project_typologies, get_project_wings,
    get_wing_inventory, resolve_project_candidates_from_text,
)
from services.property_clarification_service import apply_clarification_contract


def requested_home_types(text):
    # "s?" -- a plural mention ("3bhks", "2 bhks") names the type just as
    # specifically as the singular form; without it "which one of these has
    # 3bhks?" found no number at all and fell through to the generic (or
    # unrelated) path instead of the catalogue filter.
    return list(dict.fromkeys(re.findall(r"\b([1-6])\s*b(?:h)?ks?\b", str(text), re.I)))


_HOME_TYPE_TERMS_RE = re.compile(r"\bbhks?\b|\bhome\s*types?\b|\bconfigurations?\b", re.I)
_AVAILABILITY_CUE_RE = re.compile(r"\b(?:available|options?|have|are\s+there|offered|offer|exist)\b", re.I)


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
    types = requested_home_types(issue)
    if not types:
        return None
    if is_catalogue_home_type_query(issue) or re.search(r"\b(?:which|all|other|any|different)\s+projects?\b|\bacross\b", issue, re.I):
        return None
    # More specific unit, comparison and budget requests retain their own builders.
    if re.search(r"\b(?:wing|floor|flat\s*\d|budget|under|below|cheapest|compare|amenities|location|possession|documents)\b", issue, re.I):
        return None
    projects = customer_facing_projects(get_company_projects())
    candidates = resolve_project_candidates_from_text(projects, issue)
    if len(candidates) != 1:
        return apply_clarification_contract({"clarification_entity": "project"}, issue, history)
    project = candidates[0]
    typologies = get_project_typologies(project["id"])
    wings = get_project_wings(project["id"])
    units = [unit for wing in wings for unit in get_wing_inventory(wing["id"])]
    by_id = {str(t.get("id")): t for t in typologies}

    def matches(record, number):
        return _record_matches_type(record, number)

    lines = [f"Home types in {project['projectName']}:"]
    for number in types:
        records = [t for t in typologies if matches(t, number)]
        available = [u for u in units if matches(u, number) or matches(by_id.get(str(u.get('typologyId')), {}), number)]
        if not records and not available:
            lines.append(f"- {number}BHK: Not listed in this project's current configuration or available-unit records.")
            continue
        availability = (f"{len(available)} unit(s) currently listed as available." if available else
                        "This configuration is listed, but no units are currently listed as available.")
        lines.append(f"- {number}BHK: {availability}")
        for record in records:
            details = [str(record.get("typologyName") or f"{number}BHK")]
            for key, label in (("carpetArea", "carpet area"), ("saleableArea", "saleable area")):
                if record.get(key) is not None:
                    details.append(f"{label}: {record[key]} sq. ft.")
            if record.get("minBasePrice") is not None:
                details.append(f"base rate: INR {record['minBasePrice']} to INR {record.get('maxBasePrice') or record['minBasePrice']} ({record.get('rateType') or 'rate basis not listed'})")
            else:
                details.append("pricing is not listed")
            lines.append("  " + "; ".join(details))
    listed = list(dict.fromkeys(str(t.get("typologyName")) for t in typologies if t.get("typologyName")))
    if any(not any(matches(t, number) for t in typologies) for number in types) and listed:
        lines.append("Listed configurations: " + ", ".join(listed) + ".")
    answer = "\n".join(lines)
    return {
        "answer": answer, "route": "property", "source_status": "live_api",
        "agent_mode": "knowledge_retrieval", "used_llm": False,
        "confidence_label": "high", "source_label": "AcroBuild project and inventory records",
        "retrieval_mode": "live_project_records",
        "matched_chunks": [{"record_kind": "company_api", "source_key": f"project-{project['id']}-home-types",
                            "project": project, "typologies": typologies, "units": units, "body_text": answer}],
    }
