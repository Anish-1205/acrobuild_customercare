import json
import hashlib
from contextvars import ContextVar
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic, time

from dotenv import load_dotenv

from services.reply_language import strip_reply_language_directive
from services.cs_api_settings_service import get_cs_api_settings

from services.internal_api_log_service import (
    log_data_api_call,
    turn_cache_get,
    turn_cache_set,
)

load_dotenv()

CS_API_BASE_URL = os.getenv(
    "ACROBUILD_CS_API_BASE_URL",
    "http://10.10.1.23:8081",
).rstrip("/")
CS_API_KEY = os.getenv("ACROBUILD_CS_API_KEY", "").strip()
CS_API_COMPANY_ID = os.getenv("ACROBUILD_CS_API_COMPANY_ID", "").strip()
CS_API_TIMEOUT_SECONDS = float(
    os.getenv("ACROBUILD_CS_API_TIMEOUT_SECONDS", "2.5")
)
CS_API_CACHE_TTL_SECONDS = int(
    os.getenv("ACROBUILD_CS_API_CACHE_TTL_SECONDS", "300")
)
CS_API_LIVE_ONLY = os.getenv("ACROBUILD_CS_API_LIVE_ONLY", "true").strip().lower() not in {
    "0", "false", "no", "off",
}

_CACHE = {}
_CACHE_LOCK = Lock()
_CS_CONFIG = ContextVar("cs_api_config", default=None)


def _cs_api_defaults():
    return {"base_url": CS_API_BASE_URL, "api_key": CS_API_KEY, "company_id": CS_API_COMPANY_ID}


def _cs_api_config():
    return _CS_CONFIG.get() or get_cs_api_settings(_cs_api_defaults())

# Words that mean "the customer wants company / contact details" vs. words that
# mean "the customer is asking about property inventory". Used to decide whether
# the dense company-contact record belongs in the retrieval pool for a query.
_COMPANY_CONTACT_TERMS = frozenset({
    "contact", "phone", "call", "email", "office", "address", "located", "location",
    "website", "social", "helpline", "helpdesk", "number", "reach", "whatsapp",
    "headquarters", "hq",
})
_PROPERTY_INTENT_TERMS = frozenset({
    "property", "properties", "bhk", "flat", "flats", "home", "homes", "apartment",
    "apartments", "villa", "villas", "plot", "plots", "shop", "shops", "unit", "units",
    "wing", "wings", "floor", "floors", "price", "pricing", "rate", "rates", "cost",
    "budget", "possession", "amenity", "amenities", "availability", "available",
    "inventory", "brochure", "carpet", "saleable", "configuration", "layout",
    "project", "projects",
})
_COMPANY_DATA_SNAPSHOT_LOCK = Lock()
_COMPANY_DATA_SNAPSHOT_PATH = Path(
    os.getenv("ACROBUILD_COMPANY_DATA_PATH", "data/acrobuild_all_company_data.txt")
)

PROPERTY_TERMS = {
    "address", "amenities", "apartment", "availability", "available",
    "bhk", "builder", "carpet", "company", "construction", "contact",
    "home", "homes", "type", "types", "configuration", "configurations", "layout", "layouts", "size", "sizes",
    "email", "flat", "floor", "inventory", "location", "possession",
    "price", "project", "projects", "property", "properties", "rera", "saleable", "tower", "towers",
    "shop", "shops", "commercial", "typology", "typologies", "unit", "units", "website", "wing", "wings",
    "affordable", "budget", "recommend", "recommendation", "suggest", "best",
}
DETAIL_TERMS = {
    "amenities", "availability", "available", "bhk", "carpet",
    "home", "homes", "type", "types", "configuration", "configurations", "layout", "layouts", "size", "sizes",
    "construction", "flat", "floor", "inventory", "possession", "price", "pricing", "cost", "much",
    "address", "city", "located", "location", "saleable", "tower", "towers",
    "shop", "shops", "commercial", "typology", "typologies", "unit", "units", "wing", "wings",
    "overview", "overviews", "summary", "summarize", "explain", "details",
    "affordable", "budget", "friendly", "recommend", "recommendation", "suggest", "best",
}
INVENTORY_TERMS = {
    "availability", "available", "flat", "flats", "floor", "floors", "inventory", "unit", "units",
    "want", "looking", "need", "take", "choose", "interested",
    "book", "visit", "site", "shop", "shops", "commercial",
    "size", "sizes", "pricing", "price", "affordable", "budget", "friendly", "recommend", "suggest", "best",
}


def customer_facing_projects(projects):
    """Remove company/test rows that the CS API mixes into project data."""
    return [
        project for project in (projects or [])
        if isinstance(project, dict) and "@" not in str(project.get("address", ""))
    ]


# -----------------------------------
# CATALOGUE-WIDE FIELD FILTERING
# -----------------------------------
# Shared by every "which projects have X?" question (home type, amenity, and
# any future field the CS API exposes per project), so each one does not need
# its own project-loop-and-match code.

def build_project_record_index(record_fetcher, projects=None):
    """{project_id: {"project": record, "records": [...]}}, calling
    ``record_fetcher(project_id)`` once per live project.

    A single project's live-and-snapshot fetch failure is skipped, not fatal:
    the CS API can add a project before the on-disk snapshot is regenerated
    for it (no local fallback data yet), and that project's own timeout must
    not abort a catalogue-wide scan of every other project. Returns
    ``(index, failed)`` where ``failed`` lists the ``(project, error)`` pairs
    that were skipped, so callers can disclose partial coverage honestly
    instead of silently presenting an incomplete scan as a complete one.
    """
    index = {}
    failed = []
    for project in (projects if projects is not None else customer_facing_projects(get_company_projects())):
        try:
            index[project["id"]] = {"project": project, "records": record_fetcher(project["id"])}
        except (RuntimeError, TimeoutError) as error:
            failed.append((project, error))
    return index, failed


def filter_project_index(index, value_extractor, requested_values):
    """(matches, per_value) over a {project_id: {"project": ..., ...}} index
    (build_project_record_index()'s shape, or any per-project dict that has a
    "project" key alongside whatever field data the caller keeps).

    ``value_extractor(entry)`` turns one project's index entry into the set
    of field values it has. ``matches`` are projects whose values cover every
    requested value; ``per_value`` maps each requested value to the projects
    that have it, for an honest per-value breakdown when nothing matches all
    of them.
    """
    requested_values = list(dict.fromkeys(requested_values))
    matches = []
    per_value = {value: [] for value in requested_values}
    for entry in index.values():
        values = value_extractor(entry)
        present = [value for value in requested_values if value in values]
        for value in present:
            per_value[value].append(entry["project"])
        if requested_values and len(present) == len(requested_values):
            matches.append(entry["project"])
    return matches, per_value


# -----------------------------------
# INTERNAL HELPERS
# -----------------------------------

def _response_summary(value):
    if isinstance(value, list):
        return {"kind": "list", "record_count": len(value)}
    if isinstance(value, dict):
        return {
            "kind": "object",
            "field_count": len(value),
            "fields": sorted(str(key) for key in value.keys())[:20],
        }
    return {"kind": type(value).__name__}


def _company_scoped_path(path):
    company_id = _cs_api_config()["company_id"]
    if not company_id.isdecimal() or int(company_id) <= 0:
        raise RuntimeError("ACROBUILD_CS_API_COMPANY_ID must be a positive integer.")
    if not path.startswith("/api/cs/"):
        raise ValueError(f"Unexpected CS API path: {path}")
    return f"/api/cs/{company_id}/{path.removeprefix('/api/cs/')}"


def _request_json(path, params=None):
    config = _cs_api_config()
    if not config["api_key"]:
        raise RuntimeError("ACROBUILD_CS_API_KEY is not configured.")

    url = f"{config['base_url']}{_company_scoped_path(path)}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AcrobuildSupportAgent/1.0",
            "apiKey": config["api_key"],
        },
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started_at = monotonic()

    try:
        with opener.open(request, timeout=CS_API_TIMEOUT_SECONDS) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
            log_data_api_call(
                provider="Acrobuild CS API", endpoint=path, method="GET", params=params,
                status="completed", duration_ms=(monotonic() - started_at) * 1000,
                response_summary=_response_summary(value),
            )
            return value
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(body).get("errorMessage", body)
        except json.JSONDecodeError:
            message = body
        message = message or f"CS API request failed with HTTP {error.code}."
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, method="GET", params=params, status="failed", duration_ms=(monotonic() - started_at) * 1000, error=message)
        raise RuntimeError(message) from error
    except urllib.error.URLError as error:
        message = f"Could not reach the CS API: {error.reason}"
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, method="GET", params=params, status="failed", duration_ms=(monotonic() - started_at) * 1000, error=message)
        raise RuntimeError(message) from error
    except (socket.timeout, TimeoutError) as error:
        message = "CS API request timed out."
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, method="GET", params=params, status="failed", duration_ms=(monotonic() - started_at) * 1000, error=message)
        raise RuntimeError(message) from error
    except json.JSONDecodeError as error:
        message = "CS API returned invalid JSON."
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, method="GET", params=params, status="failed", duration_ms=(monotonic() - started_at) * 1000, error=message)
        raise RuntimeError(message) from error

def _snapshot_json_path():
    return _snapshot_path().with_suffix(".json")


def _load_snapshot_fallback(path, params=None):
    config = _cs_api_config()
    # Legacy snapshots have no origin metadata. Never reuse them for a new server.
    if config["base_url"] != CS_API_BASE_URL:
        return None
    snapshot_path = _snapshot_json_path()
    if not snapshot_path.exists():
        return None
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    company_id = config["company_id"]
    if not company_id.isdecimal() or snapshot.get("company", {}).get("id") != int(company_id):
        return None
    if path == "/api/cs/company":
        return snapshot.get("company")
    if path == "/api/cs/projects":
        return [entry.get("project", {}) for entry in snapshot.get("projects", [])]

    project_match = re.fullmatch(r"/api/cs/projects/(\d+)/(wings|typologies)", path)
    if project_match:
        project_id = int(project_match.group(1))
        section = project_match.group(2)
        project_entry = next((
            entry for entry in snapshot.get("projects", [])
            if int(entry.get("project", {}).get("id", -1)) == project_id
        ), None)
        if not project_entry:
            return None
        if section == "wings":
            return [entry.get("wing", {}) for entry in project_entry.get("wings", [])]
        return project_entry.get("project_typologies", [])

    wing_match = re.fullmatch(r"/api/cs/wings/(\d+)/(typologies|inventory)", path)
    if wing_match:
        wing_id = int(wing_match.group(1))
        section = wing_match.group(2)
        wing_entry = next((
            wing_entry
            for project_entry in snapshot.get("projects", [])
            for wing_entry in project_entry.get("wings", [])
            if int(wing_entry.get("wing", {}).get("id", -1)) == wing_id
        ), None)
        if not wing_entry:
            return None
        values = wing_entry.get(section, [])
        if section == "inventory" and str((params or {}).get("availableOnly", "false")).lower() == "true":
            available_values = [
                value for value in values
                if normalize_inventory_status(value) == "available"
            ]
            return available_values
        return values
    return None


def normalize_inventory_status(record):
    status = str(
        record.get("statusLabel")
        or record.get("availabilityStatus")
        or record.get("status")
        or ""
    ).strip().lower()
    return "available" if status in {"available", "for sale", "open"} else status


def _cached_request(path, params=None, ttl_seconds=None):
    token = _CS_CONFIG.set(_cs_api_config())
    try:
        return _cached_configured_request(path, params, ttl_seconds)
    finally:
        _CS_CONFIG.reset(token)


def _cached_configured_request(path, params=None, ttl_seconds=None):
    config = _cs_api_config()
    namespace = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    turn_key = (namespace, path, tuple(sorted((params or {}).items())))
    memoised = turn_cache_get(turn_key)
    if memoised is not None:
        summary = _response_summary(memoised)
        summary["kind"] = "turn_cache"
        log_data_api_call(
            provider="Acrobuild CS API", endpoint=path, method="GET", params=params,
            status="completed", cache_hit=True, response_summary=summary,
        )
        return memoised

    if CS_API_LIVE_ONLY:
        value = _request_json(path, params=params)
        turn_cache_set(turn_key, value)
        return value
    ttl_seconds = (
        CS_API_CACHE_TTL_SECONDS
        if ttl_seconds is None
        else ttl_seconds
    )
    cache_key = turn_key
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and time() - cached["stored_at"] < ttl_seconds:
            log_data_api_call(
                provider="Acrobuild CS API",
                endpoint=path,
                method="GET",
                params=params,
                status="cached",
                cache_hit=True,
                response_summary=_response_summary(cached["value"]),
            )
            return cached["value"]

    try:
        value = _request_json(path, params=params)
    except RuntimeError:
        fallback_value = _load_snapshot_fallback(path, params=params)
        if fallback_value is not None:
            log_data_api_call(
                provider="Acrobuild CS API snapshot",
                endpoint=path,
                method="GET",
                params=params,
                status="cached",
                cache_hit=True,
                response_summary=_response_summary(fallback_value),
            )
            return fallback_value
        if cached is not None:
            return cached["value"]
        raise
    with _CACHE_LOCK:
        _CACHE[cache_key] = {
            "stored_at": time(),
            "value": value,
        }
    turn_cache_set(turn_key, value)
    return value


def _words(value):
    return {
        word.strip(".,?!:;()[]{}").lower()
        for word in str(value or "").split()
        if word.strip(".,?!:;()[]{}")
    }


def _matches_project(query, project):
    searchable = " ".join(
        str(project.get(key, "") or "")
        for key in (
            "projectName", "projectCode", "address", "locality", "city",
        )
    ).lower()
    ignored_words = {
        "any", "are", "company", "do", "does", "have", "how", "much",
        "show", "tell", "the", "there", "what", "which", "with", "you",
    }
    relevant_words = [
        word for word in (_words(query) - PROPERTY_TERMS - ignored_words)
        if len(word) >= 3 and not (word.endswith("bhk") and word[:-3].isdigit())
    ]
    return bool(relevant_words) and all(word in searchable for word in relevant_words)


def _normalized_project_text(value):
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    # Customers commonly transliterate the catalogue brand with a "v" even
    # though the project records use "Vishwajeet". Treat that spelling as the
    # same token without fuzzy-matching unrelated project words.
    aliases = {
        "vishvajeet": "vishwajeet",
    }
    return " ".join(aliases.get(token, token) for token in tokens)


def resolve_project_candidates_from_text(projects, text):
    """Return the best project-name candidates mentioned by ``text``.

    A one-item result is a resolved project. Multiple items mean that the
    supplied name fragment is ambiguous. An empty result means that no project
    name was found. Keeping all three states prevents callers from collapsing
    an ambiguous fragment into a blind "which project?" prompt.
    """
    explicit_scopes = re.findall(r"\b(?:selected|requested)\s+project:\s*([^\n.]+)", str(text or ""), re.I)
    if explicit_scopes:
        text = explicit_scopes[-1]
    normalized_text = _normalized_project_text(text)
    if not normalized_text:
        return []
    padded_text = f" {normalized_text} "
    named_matches = []
    valid_projects = [project for project in projects or [] if isinstance(project, dict)]
    for project in valid_projects:
        name = str(project.get("projectName", "") or "").strip()
        normalized_name = _normalized_project_text(name)
        if normalized_name and f" {normalized_name} " in padded_text:
            named_matches.append((len(normalized_name.split()), len(normalized_name), project))
    if named_matches:
        named_matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
        # A suffixed name subsumes its base name, but two independent exact
        # names are ambiguous and must both be offered to the customer.
        longest = []
        for _, _, project in named_matches:
            name = _normalized_project_text(project.get("projectName", ""))
            if not any(_normalized_project_text(p.get("projectName", "")).startswith(name + " ") for p in longest):
                longest.append(project)
        return longest

    query_tokens = set(normalized_text.split())
    generic_tokens = {"project", "projects", "property", "properties", "the", "vishwajeet"}
    token_candidates = []
    for project in valid_projects:
        name_tokens = set(_normalized_project_text(project.get("projectName", "")).split())
        distinctive = name_tokens - generic_tokens
        overlap = query_tokens.intersection(distinctive)
        if distinctive and overlap:
            token_candidates.append((len(overlap), len(distinctive), project))
    if token_candidates:
        best_overlap = max(item[0] for item in token_candidates)
        best = [item for item in token_candidates if item[0] == best_overlap]
        # A fragment such as "Empire" also matches "Empire NX". Only a
        # full catalogue name (handled above) can prefer the base project.
        if len(best) == 1:
            return [best[0][2]]
        return [item[2] for item in best]

    # Incomplete but recognizable name tokens ("preci", "mysp") narrow the
    # option list without fuzzy-matching unrelated names.
    partial_candidates = []
    for project in valid_projects:
        names = set(_normalized_project_text(project.get("projectName", "")).split()) - generic_tokens
        if any(len(token) >= 3 and token not in generic_tokens and name.startswith(token)
               for token in query_tokens for name in names):
            partial_candidates.append(project)
    if partial_candidates:
        return partial_candidates

    # A shared brand token is intentionally not distinctive enough to resolve
    # one project, but it is exactly what we need to enumerate candidates for a
    # clarification (for example bare "vishvajeet").
    fallback_query_tokens = query_tokens - {
        "project", "projects", "property", "properties", "the",
    }
    fallback_candidates = []
    for project in valid_projects:
        name_tokens = set(_normalized_project_text(project.get("projectName", "")).split())
        overlap = fallback_query_tokens.intersection(name_tokens)
        if overlap:
            fallback_candidates.append((len(overlap), project))
    if not fallback_candidates:
        return []
    best_overlap = max(item[0] for item in fallback_candidates)
    return [item[1] for item in fallback_candidates if item[0] == best_overlap]


def resolve_project_from_text(projects, text):
    """Resolve one explicitly named project, preferring the longest exact name.

    Longest-name priority is essential for catalogues that contain both a base
    project and a suffixed project, such as Empire and Empire NX.
    """
    candidates = resolve_project_candidates_from_text(projects, text)
    return candidates[0] if len(candidates) == 1 else None


def _format_record(label, record, fields):
    parts = [
        f"{name}: {record.get(key)}"
        for key, name in fields
        if record.get(key) not in (None, "")
    ]
    return f"{label}: " + "; ".join(parts)


def _knowledge_chunk(title, excerpt, source_key):
    return {
        "title": title,
        "record_kind": "company_api",
        "category": "AcroBuild property data",
        "source_name": "AcroBuild CS API",
        "source_key": source_key,
        "url": "",
        "excerpt": excerpt,
        "body_text": excerpt,
        "score": 100.0,
        "overlap_terms": [],
        "strong_overlap_terms": [],
    }


# -----------------------------------
# PUBLIC API
# -----------------------------------

def is_cs_api_configured():
    config = _cs_api_config()
    return bool(config["base_url"] and config["api_key"] and config["company_id"].isdecimal()
                and int(config["company_id"]) > 0)


def get_company_projects():
    projects = _cached_request("/api/cs/projects")
    return projects if isinstance(projects, list) else []


def get_project_wings(project_id):
    wings = _cached_request(f"/api/cs/projects/{int(project_id)}/wings")
    return wings if isinstance(wings, list) else []


def get_project_amenities(project_id):
    amenities = _cached_request(f"/api/cs/projects/{int(project_id)}/amenities")
    return amenities if isinstance(amenities, list) else []


def get_project_typologies(project_id):
    records = _cached_request(f"/api/cs/projects/{int(project_id)}/typologies")
    return records if isinstance(records, list) else []


def get_wing_typologies(wing_id):
    typologies = _cached_request(f"/api/cs/wings/{int(wing_id)}/typologies")
    return typologies if isinstance(typologies, list) else []


def get_wing_inventory(wing_id, available_only=True):
    inventory = _cached_request(
        f"/api/cs/wings/{int(wing_id)}/inventory",
        params={"availableOnly": str(bool(available_only)).lower()},
        ttl_seconds=30,
    )
    return inventory if isinstance(inventory, list) else []

def search_company_knowledge(query, max_projects=20):
    if not is_cs_api_configured():
        return []

    query = strip_reply_language_directive(query)
    query_words = _words(query)
    if any(word.startswith("shop") for word in query_words) or query_words.intersection({"store", "stores", "commercial"}):
        query_words.update({"shop", "shops"})
    has_bhk_query = any(
        word.endswith("bhk") and word[:-3].isdigit()
        for word in query_words
    )
    if has_bhk_query:
        query_words.add("bhk")

    is_project_count_query = (
        bool(query_words.intersection({"project", "projects"}))
        and bool(query_words.intersection({"how", "many", "count", "number", "total", "available"}))
        and not bool(query_words.intersection({
            "bhk", "flat", "flats", "home", "homes", "shop", "shops", "unit", "units",
            "wing", "wings", "floor", "floors", "price", "pricing", "budget",
        }))
    )

    # The company contact record is a single dense blob. Keep it out of the
    # retrieval pool for property-shaped queries, where it used to win on its
    # fixed score and get pasted verbatim; only surface it when the query is
    # actually about the company / how to reach it. See
    # docs/BYTECODE_FALLBACK_USAGE.md.
    wants_contact_info = bool(query_words.intersection(_COMPANY_CONTACT_TERMS))
    looks_like_property_query = bool(query_words.intersection(_PROPERTY_INTENT_TERMS))
    suppress_company_chunk = is_project_count_query or (
        looks_like_property_query and not wants_contact_info
    )

    chunks = []
    if suppress_company_chunk:
        company = None
    else:
        try:
            company = _cached_request("/api/cs/company")
        except RuntimeError:
            company = None
    if isinstance(company, dict):
        company_chunk = _knowledge_chunk(
            "Company contact details",
            _format_record(
                "Company",
                company,
                (
                    ("companyName", "name"),
                    ("businessName", "business name"),
                    ("address", "address"),
                    ("city", "city"),
                    ("zipCode", "PIN/zip"),
                    ("phoneNo", "phone"),
                    ("contactEmail", "email"),
                    ("websiteUrl", "website"),
                    ("socialUrls", "social links"),
                ),
            ),
            "acrobuild-cs-company",
        )
        company_chunk["company"] = company
        # `_knowledge_chunk` stamps a fixed score of 100; that let the contact
        # blob outrank genuine project / article matches. Keep it modest so it
        # only wins when nothing substantive matched.
        company_chunk["score"] = 12.0
        chunks.append(company_chunk)

    projects = customer_facing_projects(_cached_request("/api/cs/projects"))
    project_fields = (
        ("projectName", "name"),
        ("projectCode", "code"),
        ("address", "address"),
        ("locality", "locality"),
        ("city", "city"),
        ("reraNo", "RERA"),
        ("propertyDetails", "property details"),
        ("projectType", "type"),
        ("isPublished", "published"),
    )
    if projects:
        project_chunk = _knowledge_chunk(
            "Company projects",
            "\n".join(
                _format_record("Project", project, project_fields)
                for project in projects[:max_projects]
            ),
            "acrobuild-cs-projects",
        )
        project_chunk["record_count"] = len(projects)
        project_chunk["projects"] = projects
        project_chunk["project_names"] = [
            str(project.get("projectName", "")).strip()
            for project in projects
            if isinstance(project, dict)
            and str(project.get("projectName", "")).strip()
        ]
        chunks.append(project_chunk)
    if is_project_count_query:
        return chunks
    normalized_query = str(query or "").lower()
    resolved_project = resolve_project_from_text(projects, query)
    matching_projects = [resolved_project] if resolved_project else [
        project for project in projects
        if (
            str(project.get("projectName", "") or "").strip().lower() in normalized_query
            or _matches_project(query, project)
            or any(
                len(word) >= 3
                and word in _words(project.get("projectName", ""))
                for word in query_words
                if word not in {"the", "this", "that", "will", "want", "choose", "select", "project", "show"}
            )
        )
        and str(project.get("projectName", "") or "").strip()
    ]
    has_property_query = bool(query_words.intersection(PROPERTY_TERMS) or has_bhk_query)
    if not has_property_query and not matching_projects:
        return []
    if not query_words.intersection(DETAIL_TERMS) and not matching_projects:
        return chunks

    if not matching_projects:
        matching_projects = projects

    for project in matching_projects[:max_projects]:
        project_id = project.get("id")
        if project_id is None:
            continue
        wings = _cached_request(
            f"/api/cs/projects/{project_id}/wings"
        )
        typologies = _cached_request(
            f"/api/cs/projects/{project_id}/typologies"
        )
        if not isinstance(wings, list):
            wings = []
        if not isinstance(typologies, list):
            typologies = []


        detail_lines = [
            _format_record("Project", project, project_fields)
        ]
        available_inventory = []
        detail_lines.extend(
            _format_record(
                "Wing",
                wing,
                (
                    ("name", "name"),
                    ("code", "code"),
                    ("constructionStatus", "construction status"),
                    ("expectedPossesionDate", "expected possession epoch ms"),
                    ("totalFloors", "floors"),
                    ("saleableUnits", "saleable units"),
                    ("saleableArea", "saleable area"),
                ),
            )
            for wing in wings
        )
        detail_lines.extend(
            _format_record(
                "Typology",
                typology,
                (
                    ("typologyName", "name"),
                    ("typologyType", "type"),
                    ("carpetArea", "carpet area"),
                    ("saleableArea", "saleable area"),
                    ("unitAmenities", "amenities"),
                    ("rateType", "rate type"),
                    ("minBasePrice", "minimum base price"),
                    ("maxBasePrice", "maximum base price"),
                ),
            )
            for typology in typologies
        )

        if query_words.intersection(INVENTORY_TERMS):
            for wing in wings:
                wing_id = wing.get("id")
                if wing_id is None:
                    continue
                inventory = _cached_request(
                    f"/api/cs/wings/{wing_id}/inventory",
                    params={"availableOnly": "true"},
                    ttl_seconds=30,
                )
                if not isinstance(inventory, list):
                    continue
                available_inventory.extend(inventory)
                detail_lines.append(
                    f"Available inventory in {wing.get('name', wing_id)}: "
                    f"{len(inventory)} unit(s)."
                )
                detail_lines.extend(
                    _format_record(
                        "Available unit",
                        unit,
                        (
                            ("unitNumber", "unit"),
                            ("floorNumber", "floor"),
                            ("typologyName", "typology"),
                            ("statusLabel", "status"),
                            ("carpetArea", "carpet area"),
                            ("saleableArea", "saleable area"),
                        ),
                    )
                    for unit in inventory[:20]
                )

        project_name = project.get("projectName", str(project_id))
        detail_chunk = _knowledge_chunk(
            f"{project_name} live property details",
            "\n".join(detail_lines),
            f"acrobuild-cs-project-{project_id}",
        )
        detail_chunk["project_name"] = project_name
        detail_chunk["project"] = project
        detail_chunk["wings"] = wings
        detail_chunk["typologies"] = typologies
        detail_chunk["available_inventory"] = available_inventory
        detail_chunk["inventory_loaded"] = bool(query_words.intersection(INVENTORY_TERMS))
        chunks.append(detail_chunk)
    return chunks


def get_cs_api_status():
    return {
        "configured": is_cs_api_configured(),
        "base_url": _cs_api_config()["base_url"],
        "api_key_present": bool(_cs_api_config()["api_key"]),
    }
# -----------------------------------
# COMPLETE COMPANY DATA SNAPSHOT
# -----------------------------------

def _snapshot_path():
    path = _COMPANY_DATA_SNAPSHOT_PATH
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def _append_text_value(lines, label, value, indent=0):
    prefix = "  " * indent
    if isinstance(value, dict):
        lines.append(f"{prefix}{label}:")
        if not value:
            lines.append(f"{prefix}  (empty)")
        for key, nested_value in value.items():
            _append_text_value(lines, str(key), nested_value, indent + 1)
        return
    if isinstance(value, list):
        lines.append(f"{prefix}{label}: {len(value)} item(s)")
        if not value:
            lines.append(f"{prefix}  (empty)")
        for index, nested_value in enumerate(value, start=1):
            _append_text_value(lines, f"Item {index}", nested_value, indent + 1)
        return
    lines.append(f"{prefix}{label}: {value if value not in (None, '') else '(empty)'}")


def export_all_company_data_to_text():
    """Fetch and store all company, project, wing, typology, and inventory data."""
    company = _cached_request("/api/cs/company")
    projects = get_company_projects()
    snapshot = {
        "company": company if isinstance(company, dict) else {},
        "projects": [],
    }
    for project in projects:
        project_id = project.get("id")
        project_entry = {"project": project, "project_typologies": [], "wings": []}
        if project_id is not None:
            project_typologies = _cached_request(f"/api/cs/projects/{int(project_id)}/typologies")
            project_entry["project_typologies"] = project_typologies if isinstance(project_typologies, list) else []
            for wing in get_project_wings(project_id):
                wing_id = wing.get("id")
                wing_entry = {"wing": wing, "typologies": [], "inventory": []}
                if wing_id is not None:
                    wing_entry["typologies"] = get_wing_typologies(wing_id)
                    wing_entry["inventory"] = get_wing_inventory(wing_id, available_only=False)
                project_entry["wings"].append(wing_entry)
        snapshot["projects"].append(project_entry)

    lines = [
        "ACROBUILD COMPLETE COMPANY DATA",
        f"Generated: {datetime.now(timezone.utc).astimezone().isoformat()}",
        "This file contains parsed company data only. The API key is never stored.",
        "=" * 88,
        "",
    ]
    _append_text_value(lines, "Company", snapshot["company"])
    lines.extend(["", "=" * 88, ""])
    _append_text_value(lines, "Projects", snapshot["projects"])
    lines.append("")

    destination = _snapshot_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    json_destination = _snapshot_json_path()
    json_temporary = json_destination.with_suffix(json_destination.suffix + ".tmp")
    with _COMPANY_DATA_SNAPSHOT_LOCK:
        temporary.write_text("\n".join(lines), encoding="utf-8")
        json_temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)
        json_temporary.replace(json_destination)
    return str(destination)


def refresh_company_data_snapshot_async():
    from threading import Thread

    worker = Thread(target=export_all_company_data_to_text, daemon=True, name="company-data-snapshot")
    worker.start()
    return worker


def get_company_data_snapshot_path():
    return str(_snapshot_path())
