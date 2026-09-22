"""Reverse amenity lookup: amenity -> projects, over live CS API data only.

The forward direction ("what amenities does project X have") is handled by
api_context.build_grounded_project_amenities_assist. This module covers the
reverse question ("which projects have a gym", "where can I find a swimming
pool"), plus the single-project yes/no form ("does Vishwajeet Prime have a
gym?"), which reads exactly the same records.

Grounding rule: the only amenity names this module will ever talk about are
the iconName values the live /api/cs/projects/{id}/amenities endpoint
returns. A customer word that does not resolve to one of those live values
produces no match at all (the caller falls through), never a guess -- the
alias table below maps customer vocabulary onto a *fragment that must itself
occur in a live amenity name*, so an alias can never invent an amenity.
"""
import re

from services.acrobuild_company_service import (
    build_project_record_index,
    customer_facing_projects,
    filter_project_index,
    get_company_projects,
    get_project_amenities,
    resolve_project_candidates_from_text,
)

# Tokens that carry no distinguishing meaning inside a live amenity name, so
# requiring the customer to have typed them would lose obvious matches
# ("play area" vs the live "Children's Playing Area").
_AMENITY_STOPWORDS = frozenset({"and", "the", "area", "areas", "of", "for", "a", "s"})

# Customer vocabulary -> a literal fragment that must appear in a live amenity
# name. Never a standalone amenity: if the fragment matches nothing live, the
# alias contributes nothing.
_ALIASES = (
    (r"\bgyms?\b|\bgymnasium\b|\bfitness\s+(?:centre|center|room)\b|\bworkout\b", "gym"),
    (r"\bswimming\s*pools?\b|\bpools?\b|\bswim\b|\bswimming\b", "swimming pool"),
    (r"\blifts?\b|\belevators?\b", "lift"),
    (r"\bcctv\b|\bsecurity\s+cameras?\b|\bcameras?\b|\bsurveillance\b", "cctv"),
    (r"\bsecurity\s+(?:guards?|personnel|staff)\b|\bwatchman\b", "security personnel"),
    (r"\bplay\s*(?:ground|area)\b|\bkids?\s+(?:play\s*)?area\b|\bchildrens?\s+play\w*\b", "playing area"),
    (r"\byoga\b|\bmeditation\b", "yoga"),
    (r"\bjogging\b|\brunning\s+track\b", "jogging track"),
    (r"\bgardens?\b|\bparks?\b|\bgreen\s+space\b", "park"),
    (r"\bclub\s*house\b|\bcommunity\s+(?:hall|centre|center|house)\b", "community house"),
    (r"\bbanquet\b|\bmultipurpose\s+hall\b|\bfunction\s+hall\b", "multipurpose hall"),
    (r"\bpower\s*back\s*up\b|\bgenerators?\b|\binverters?\b", "power backup"),
    (r"\bsolar\b", "solar"),
    (r"\brain\s*water\s+harvesting\b", "rain water harvesting"),
    (r"\bparking\b|\bcar\s+park\w*\b", "parking"),
    (r"\bvisitor\s+parking\b|\bguest\s+parking\b", "visitor parking"),
    (r"\bgated\b", "gated community"),
    (r"\bwifi\b|\bwi-?fi\b|\bbroadband\b|\binternet\b", "internet"),
    (r"\bfire\s+(?:alarm|safety|fighting)\b", "fire"),
    (r"\bsenior\s+citizens?\b|\belderly\b", "senior citizen"),
    (r"\bwalkways?\b|\bpaved\s+walkway\b", "paved walkway"),
    (r"\bparty\s+lawn\b|\blawn\b", "party lawn"),
    (r"\bcricket\b", "cricket"),
    (r"\bfootball\b|\bsoccer\b", "football"),
    (r"\bbadminton\b", "badminton"),
    (r"\bcarrom\b", "carrom"),
    (r"\bbilliards?\b|\bbillards?\b|\bsnooker\b", "billards"),
    (r"\bterraces?\b", "terrace"),
    (r"\bearthquake\b|\bseismic\b", "earthquake"),
    (r"\bgas\s+(?:pipe|pipeline|connection)\b|\bpiped\s+gas\b", "gas pipe"),
    (r"\bwater\s+supply\b", "water supply"),
    (r"\belectricity\b|\bpower\s+supply\b", "electricity supply"),
    (r"\bwaste\b|\bgarbage\b|\btrash\b", "waste"),
    (r"\bsewage\b|\bstp\b", "sewage"),
    (r"\bstreet\s+lamps?\b|\bstreet\s+lights?\b", "street lamps"),
    (r"\blobby\b|\bentrance\s+lobby\b", "lobby"),
    (r"\bmaintenance\b|\bmantainence\b", "mantainence"),
    (r"\btelecom\b|\bcable\s+connection\b|\bdth\b", "telecom"),
)

# The customer is asking about a set of projects rather than about one named
# project: "which projects", "where can I find", "any project with", etc.
_REVERSE_SUBJECT_RE = re.compile(
    r"\b(?:projects?|properties|property|societ(?:y|ies)|buildings?|flats?|homes?|apartments?)\b",
    re.IGNORECASE,
)
_REVERSE_CUE_RE = re.compile(
    r"\b(?:which|what|any|anywhere|all|list|show|find|do\s+you\s+have|is\s+there|are\s+there)\b",
    re.IGNORECASE,
)
_WHERE_CUE_RE = re.compile(r"\bwhere\s+can\s+i\b|\bwhere\s+(?:do\s+you\s+have|is|are)\b", re.IGNORECASE)
# "does <project> have a gym" -- the single-project yes/no form.
_YES_NO_CUE_RE = re.compile(r"\b(?:does|do|is|are|has|have|got)\b", re.IGNORECASE)


def _normalize(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _significant_tokens(normalized_name):
    return [token for token in normalized_name.split()
            if len(token) >= 3 and token not in _AMENITY_STOPWORDS]


def live_amenity_index():
    """{project_id: {"project": record, "amenities": [canonical names]}} built
    from the live catalogue. Every name here came off the CS API.

    Uses the shared, per-project-resilient fetcher (services/acrobuild_company_service.py):
    a project whose live amenities cannot be fetched right now (e.g. it was
    added to the catalogue after the on-disk snapshot was last regenerated,
    so there is no fallback for it yet) is left out of the index instead of
    aborting the whole reverse-amenity search."""
    raw_index, _failed = build_project_record_index(
        get_project_amenities, projects=customer_facing_projects(get_company_projects()),
    )
    return {
        project_id: {
            "project": entry["project"],
            "amenities": list(dict.fromkeys(
                str(record.get("iconName", "")).strip()
                for record in entry["records"]
                if isinstance(record, dict) and str(record.get("iconName", "")).strip()
            )),
        }
        for project_id, entry in raw_index.items()
    }


def live_amenity_names(index):
    names = []
    for entry in index.values():
        names.extend(entry["amenities"])
    return list(dict.fromkeys(names))


def match_amenity_terms(text, live_names):
    """Live amenity names the customer's words actually refer to.

    Three ways a live name matches, all anchored on live values:
      1. the whole live name appears in the message ("swimming pool"),
      2. every significant token of the live name appears in the message, or
      3. an alias fragment matched the message AND that fragment occurs in
         this live name.
    """
    normalized_text = _normalize(text)
    if not normalized_text:
        return []
    padded = f" {normalized_text} "
    alias_fragments = [fragment for pattern, fragment in _ALIASES
                       if re.search(pattern, normalized_text, re.IGNORECASE)]
    matched = []
    for name in live_names:
        normalized_name = _normalize(name)
        if not normalized_name:
            continue
        tokens = _significant_tokens(normalized_name)
        hit = (
            f" {normalized_name} " in padded
            or (tokens and all(f" {token} " in padded for token in tokens))
            or any(fragment in normalized_name for fragment in alias_fragments)
        )
        if hit:
            matched.append(name)
    # Prefer the most specific live names: if "Swimming Pool" matched, do not
    # also report "Baby Swimming Area" off the same alias fragment.
    specific = [name for name in matched
                if not any(other != name and _normalize(other) in _normalize(name)
                           for other in matched)]
    return list(dict.fromkeys(specific or matched))


def is_reverse_amenity_query(text):
    """Deterministic shape test only -- whether an amenity is actually named
    is checked separately against live data by the caller."""
    text = str(text or "")
    if _WHERE_CUE_RE.search(text):
        return True
    return bool(_REVERSE_SUBJECT_RE.search(text) and _REVERSE_CUE_RE.search(text))


def is_amenity_lookup_query(text, live_names):
    """True when this turn should be handled by the amenity search path: it is
    shaped like a reverse/yes-no amenity question AND names a live amenity."""
    text = str(text or "")
    if not match_amenity_terms(text, live_names):
        return False
    return bool(is_reverse_amenity_query(text) or _YES_NO_CUE_RE.search(text))


def known_localities(index):
    """Real city/locality values off the live project records -- the only
    place names this module will ever scope a search to."""
    values = set()
    for entry in index.values():
        for key in ("city", "locality"):
            value = str(entry["project"].get(key, "") or "").strip()
            if value:
                values.add(value)
    return values


def scope_index_to_locality(index, text):
    """(scoped index, locality name) when the message names a live city or
    locality, else (index, ""). Without this, "which projects in Pune have a
    gym" would be answered from the whole catalogue."""
    normalized_text = f" {_normalize(text)} "
    for locality in sorted(known_localities(index), key=len, reverse=True):
        if f" {_normalize(locality)} " in normalized_text:
            scoped = {
                key: entry for key, entry in index.items()
                if locality.lower() in {
                    str(entry["project"].get("city", "") or "").strip().lower(),
                    str(entry["project"].get("locality", "") or "").strip().lower(),
                }
            }
            if scoped:
                return scoped, locality
    return index, ""


def projects_with_amenities(index, terms):
    """Projects whose live amenity list contains every requested term, plus a
    per-term breakdown used when nothing has all of them. A thin wrapper
    around the shared filter_project_index() (services/acrobuild_company_service.py)
    that every "which projects have X?" question now goes through."""
    return filter_project_index(index, lambda entry: entry["amenities"], terms)


def resolve_named_project(text):
    """One explicitly named project, or None -- decides yes/no vs reverse form."""
    projects = customer_facing_projects(get_company_projects())
    candidates = resolve_project_candidates_from_text(projects, text)
    return candidates[0] if len(candidates) == 1 else None
