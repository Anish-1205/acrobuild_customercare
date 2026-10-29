"""Defensive cleaning of CS API records, applied once where they are fetched.

The CS API's data has known problems (see the 2026-10-29 audit in CHANGELOG.md): stray spaces and mixed
casing in names, misspelt amenity names, duplicate unit numbers, home types with rates swapped or missing,
payment-plan names that are milestone sentences. Everything downstream works on records cleaned here, so
no answer has to defend against them again.
"""
import re

AMENITY_SPELLING = {
    "mantainence": "Maintenance", "maintainence": "Maintenance", "enterance lobby": "Entrance Lobby",
    "pool & billards": "Pool & Billiards", "accupressure park": "Acupressure Park",
}


def text(value):
    """Trimmed, single-spaced text; "" for None."""
    return " ".join(str(value).split()) if value is not None else ""


def _positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _with_text(record, keys):
    cleaned = dict(record)
    for key in keys:
        if key in cleaned and isinstance(cleaned[key], str):
            cleaned[key] = text(cleaned[key])
    return cleaned


def clean_projects(records):
    """Projects with an id and a name, string fields trimmed."""
    return [_with_text(p, ("projectName", "city", "locality", "address", "location", "reraNo"))
            for p in records or [] if isinstance(p, dict) and p.get("id") is not None and text(p.get("projectName"))]


def clean_wings(records):
    cleaned = []
    for wing in records or []:
        if not isinstance(wing, dict) or wing.get("id") is None:
            continue
        wing = _with_text(wing, ("name", "code", "constructionStatus", "developmentType"))
        floors = _positive(wing.get("totalFloors"))
        wing["totalFloors"] = int(floors) if floors and floors < 200 else None  # 0 or 999 floors is a data error
        cleaned.append(wing)
    return cleaned


def clean_typologies(records):
    """Home types with sane areas and rates: non-positive values become None, carpet/saleable and min/max
    rates are put back in order when swapped, and a lone rate fills both ends."""
    cleaned = []
    for typology in records or []:
        if not isinstance(typology, dict) or typology.get("id") is None:
            continue
        typology = _with_text(typology, ("typologyName", "typologyType", "rateType"))
        carpet, saleable = _positive(typology.get("carpetArea")), _positive(typology.get("saleableArea"))
        if carpet and saleable and carpet > saleable:
            carpet, saleable = saleable, carpet
        low, high = _positive(typology.get("minBasePrice")), _positive(typology.get("maxBasePrice"))
        if low and high and low > high:
            low, high = high, low
        typology.update(carpetArea=carpet, saleableArea=saleable, minBasePrice=low or high, maxBasePrice=high or low)
        cleaned.append(typology)
    return cleaned


def clean_inventory(records):
    """Units counted once: the API repeats unit numbers within a wing (e.g. Pearl 201, 204, 306...)."""
    seen, cleaned = set(), []
    for unit in records or []:
        if not isinstance(unit, dict) or unit.get("id") is None:
            continue
        key = (unit.get("wingId"), text(unit.get("unitNumber")).lower(), unit.get("floorNumber"),
               unit.get("typologyId")) if text(unit.get("unitNumber")) else ("id", unit["id"])
        if key in seen or ("id", unit["id"]) in seen:
            continue
        seen.update({key, ("id", unit["id"])})
        cleaned.append(_with_text(unit, ("typologyName", "typologyType", "statusLabel")))
    return cleaned


def amenity_name(name):
    cleaned = text(name)
    return AMENITY_SPELLING.get(cleaned.lower(), cleaned)


def plan_name(name, schedule_type):
    """A display name for a payment plan; some are milestone sentences ("1% To be paid to the promoter...")."""
    cleaned = text(name)
    if not cleaned or re.search(r"%|to be paid", cleaned, re.IGNORECASE) or len(cleaned) > 60:
        return f"{text(schedule_type) or 'Payment'} plan"
    return cleaned
