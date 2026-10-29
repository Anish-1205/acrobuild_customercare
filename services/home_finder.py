"""Home search the way buyers ask: city / locality, BHK, size, budget in lakhs, ready to move.

Pure functions over CS API records, so the matching rules are testable without the API.
Prices are estimates: the CS API's base rate is per saleable sq ft (home names carry the
saleable size, e.g. "2BHK 1254(SQ.FT)"), so total = saleable area x rate, before taxes and charges.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime

# Cities buyers commonly name; any not in our project data is answered "we don't build there".
KNOWN_CITIES = (
    "navi mumbai", "mumbai", "thane", "pune", "kalyan", "dombivli", "ambernath", "badlapur", "nashik", "nagpur",
    "aurangabad", "kolhapur", "delhi", "noida", "gurgaon", "gurugram", "bangalore", "bengaluru", "hyderabad",
    "chennai", "kolkata", "ahmedabad", "surat", "goa", "jaipur", "lucknow", "indore", "bhopal",
)
# Localities buyers name, by city, so "flat in Magarpatta" is understood as Pune even when no project is there.
# shortcut: a hand-kept list for the cities we sell in; replace with a geocoder if we expand to more cities.
LOCALITIES = {
    "pune": (
        "aundh", "baner", "balewadi", "bavdhan", "bibwewadi", "camp", "chakan", "charholi", "chinchwad", "dhanori",
        "dhayari", "hadapsar", "hinjewadi", "kalyani nagar", "karve nagar", "katraj", "keshav nagar", "kharadi",
        "kondhwa", "koregaon park", "kothrud", "lohegaon", "magarpatta", "manjri", "moshi", "mundhwa", "nibm",
        "nigdi", "pashan", "pimple nilakh", "pimple saudagar", "pimpri", "punawale", "ravet", "shivaji nagar",
        "sinhagad road", "sus", "talegaon", "tathawade", "undri", "viman nagar", "wagholi", "wakad", "wanowrie",
        "warje", "yerwada",
    ),
    "thane": (
        "ambernath", "badlapur", "balkum", "bhiwandi", "diva", "dombivli", "ghodbunder road", "kalwa", "kalyan",
        "kasarvadavali", "kolshet", "majiwada", "mumbra", "shahad", "titwala", "ulhasnagar", "varap",
        "vartak nagar", "wagle estate",
    ),
    "mumbai": (
        "andheri", "bandra", "borivali", "chembur", "dadar", "ghatkopar", "goregaon", "juhu", "kandivali", "kurla",
        "malad", "mira road", "mulund", "powai", "santacruz", "vikhroli", "worli",
    ),
    "navi mumbai": ("airoli", "belapur", "ghansoli", "kamothe", "kharghar", "nerul", "panvel", "ulwe", "vashi"),
}
LOCALITY_CITY = {locality: city for city, names in LOCALITIES.items() for locality in names}
SIZE_TOLERANCE = 0.15
WIDE_PRICE_RATIO = 1.6  # above this, a price range is shown as "from X" (CS API rates span up to 2x)
SEARCH_RE = re.compile(
    r"\b(looking|want|need|show|find|search|suggest|options?|property|properties|flats?|homes?|apartments?|"
    r"houses?|bhk|rk|budget|lakhs?|lacs?|crores?|sq\.? ?ft|sqft|square|ready|possession|projects?|near|"
    r"around|side|anything|available)\b", re.I)


@dataclass
class Criteria:
    place: str = ""                 # first city or locality the customer named
    places: tuple = ()              # every place named ("Wakad or Hinjewadi")
    bhk: float | None = None        # 1, 2, 2.5, 3...; 0.5 for 1 RK (the first one named)
    bhks: tuple = ()                # every BHK named ("2 or 3 bhk", "2bhk and 3bhk")
    size: float | None = None       # "around N sq ft"
    size_min: float | None = None   # "above N sq ft"
    size_max: float | None = None   # "under N sq ft"
    carpet: bool = False            # sizes are carpet area, not saleable
    budget_max: float | None = None  # rupees
    budget_min: float | None = None
    ready: bool = False

    def any(self):
        return bool(self.place or self.bhk is not None or self.has_size() or self.budget_max or self.budget_min
                    or self.ready)

    def has_size(self):
        return bool(self.size or self.size_min or self.size_max)

    def describe(self):
        """ "2BHK homes under ₹50 lakh in Pune", "homes above 1,200 sq ft carpet", "1BHK homes ready to move"."""
        parts = []
        kinds = self.bhks or ((self.bhk,) if self.bhk is not None else ())
        if kinds:
            parts.append(" or ".join("1 RK" if k == 0.5 else f"{k:g}BHK" for k in kinds))
        parts.append("homes")
        unit = "sq ft carpet" if self.carpet else "sq ft"
        if self.size_min and self.size_max:
            parts.append(f"of {self.size_min:,.0f}-{self.size_max:,.0f} {unit}")
        elif self.size_min:
            parts.append(f"above {self.size_min:,.0f} {unit}")
        elif self.size_max:
            parts.append(f"under {self.size_max:,.0f} {unit}")
        elif self.size:
            parts.append(f"around {self.size:,.0f} {unit}")
        if self.budget_min and self.budget_max:
            parts.append(f"for {lakhs(self.budget_min)}-{lakhs(self.budget_max)}")
        elif self.budget_max:
            parts.append(f"under {lakhs(self.budget_max)}")
        elif self.budget_min:
            parts.append(f"above {lakhs(self.budget_min)}")
        if self.ready:
            parts.append("ready to move")
        places = self.places or ((self.place,) if self.place else ())
        if places:
            parts.append("in " + " or ".join(p.title() for p in places))
        return " ".join(parts)


def lakhs(rupees):
    return f"₹{rupees / 1e7:.2f} crore" if rupees >= 1e7 else f"₹{rupees / 1e5:.0f} lakh"


def _amount(number, unit):
    value = float(number)
    return value * (1e7 if unit.lower().startswith(("cr", "crore", "karo")) else 1e5)


PLACE_ALIASES = {"poona": "pune", "puna": "pune", "poone": "pune", "bombay": "mumbai", "thana": "thane",
                 "tane": "thane", "bengaluru": "bangalore", "gurugram": "gurgaon", "hinjawadi": "hinjewadi",
                 "hinjwadi": "hinjewadi", "hinjewdi": "hinjewadi", "pimple saudagar": "pimple saudagar",
                 "kp": "koregaon park", "ghodbunder": "ghodbunder road", "gb road": "ghodbunder road"}
# Number words in English, Hindi and Marathi, as buyers type them: "two bhk", "do bhk", "pachas lakh".
NUMBER_WORDS = {
    "one": 1, "ek": 1, "two": 2, "do": 2, "don": 2, "three": 3, "teen": 3, "tin": 3, "four": 4, "char": 4,
    "chaar": 4, "five": 5, "paanch": 5, "panch": 5, "pach": 5, "six": 6, "chhe": 6, "seven": 7, "saat": 7,
    "eight": 8, "aath": 8, "nine": 9, "nau": 9, "ten": 10, "das": 10, "twenty": 20, "bees": 20, "vees": 20,
    "thirty": 30, "tees": 30, "forty": 40, "chalis": 40, "chaalis": 40, "fifty": 50, "pachas": 50,
    "pannas": 50, "sixty": 60, "saath": 60, "seventy": 70, "sattar": 70, "eighty": 80, "assi": 80,
    "ninety": 90, "nabbe": 90, "hundred": 100, "sau": 100,
}
_UNIT_WORDS = {"lakh", "lakhs", "crore", "crores", "bhk", "sqft", "square", "feet", "ready", "possession",
               "bedroom", "budget", "property", "flat", "apartment", "carpet", "above", "below", "under", "between"}

# Size units -> sq ft factor. Buyers in the north say "gaj" (square yards); some quote square metres.
_SQFT = r"(?:sq\.?\s*f(?:ee)?ts?|sq\.?\s*feets?|sqft|sft|square\s*f(?:ee|oo)ts?|sq\s*foot)"
_SQM = r"(?:sq\.?\s*m(?:trs?|tr|eters?|etres?)?|sqm|square\s*met(?:er|re)s?)"
_SQYD = r"(?:sq\.?\s*y(?:ar)?ds?|square\s*yards?|gaj|gaz)"
_SIZE_UNIT = rf"(?P<unit>{_SQFT}|{_SQM}|{_SQYD}|size)\b"
_NUM = r"(\d+(?:\.\d+)?)"
_MORE = r"(?:above|over|more\s+than|greater\s+than|at\s*least|atleast|minimum|min|starting(?:\s+from)?|from)"
_LESS = r"(?:below|under|less\s+than|up\s*to|upto|max(?:imum)?|within|till|not\s+more\s+than)"
_MONEY_UNIT = r"(lakhs?|lacs?|lakh|lac|l|cr|crores?|karod|karor)\b"


def _sqft(value, unit):
    unit = unit.lower()
    if re.fullmatch(_SQM, unit):
        return value * 10.764
    if re.fullmatch(_SQYD, unit):
        return value * 9
    return value


def _normalise(text, places):
    """Lower-case; fix spelling of places and search words; digits for number words before a unit;
    drop Indian digit-group commas ("50,00,000", "1,200"); expand "1.2k sq ft"."""
    lowered = " ".join(str(text or "").lower().split())
    for alias, place in PLACE_ALIASES.items():
        lowered = re.sub(rf"\b{alias}\b", place, lowered)
    from services.text_fuzz import correct_words
    all_places = set(places) | set(KNOWN_CITIES) | set(LOCALITY_CITY)
    place_words = {w for p in all_places for w in re.findall(r"[a-z]+", p.lower())}
    lowered = correct_words(lowered, place_words | _UNIT_WORDS, cutoff=0.8).lower()
    number = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
    lowered = re.sub(rf"\b({number})\s*(?=(?:bhk|bedroom|rk|lakhs?|lacs?|lakh|l\b|cr\b|crores?|karod))",
                     lambda m: f"{NUMBER_WORDS[m.group(1)]} ", lowered)
    lowered = re.sub(r"(?<=\d),(?=\d)", "", lowered)
    return re.sub(r"\b(\d+(?:\.\d+)?)\s*k\b(?=\s*(?:sq|sft|square|carpet|size|gaj))",
                  lambda m: f"{float(m.group(1)) * 1000:g}", lowered)


def _parse_places(lowered, places):
    found, remaining = [], lowered
    for place in sorted({p.lower() for p in places if p} | set(KNOWN_CITIES) | set(LOCALITY_CITY),
                        key=len, reverse=True):
        match = re.search(rf"\b{re.escape(place)}\b", remaining)
        if match:
            found.append((match.start(), place))
            remaining = remaining[:match.start()] + " " * len(place) + remaining[match.end():]
    return tuple(place for _, place in sorted(found))


def _parse_size(lowered, criteria):
    def value(number, match):
        return _sqft(float(number), match.group("unit"))

    if match := re.search(rf"(?:between\s+{_NUM}\s*and|{_NUM}\s*(?:-|to))\s*{_NUM}\s*{_SIZE_UNIT}", lowered):
        first = match.group(1) or match.group(2)  # "between A and B" or "A-B" / "A to B"
        low, high = sorted((value(first, match), value(match.group(3), match)))
        criteria.size_min, criteria.size_max = low, high
    elif match := (re.search(rf"{_MORE}\s*{_NUM}\s*{_SIZE_UNIT}", lowered)
                   or re.search(rf"{_NUM}\s*\+\s*{_SIZE_UNIT}", lowered)
                   or re.search(rf"{_NUM}\s*{_SIZE_UNIT}\s*(?:\+|or\s+more|and\s+above|plus|ya\s+zyada)", lowered)):
        criteria.size_min = value(match.group(1), match)
    elif match := (re.search(rf"{_LESS}\s*{_NUM}\s*{_SIZE_UNIT}", lowered)
                   or re.search(rf"{_NUM}\s*{_SIZE_UNIT}\s*(?:or\s+less|and\s+below|max|tak)", lowered)):
        criteria.size_max = value(match.group(1), match)
    elif match := re.search(rf"{_NUM}\s*{_SIZE_UNIT}", lowered):
        criteria.size = value(match.group(1), match)
    elif match := re.search(r"\bsize\s*(?:of\s*)?(?:around\s*|about\s*)?(\d{3,5})\b", lowered):
        criteria.size = float(match.group(1))
    # A home is 150-20,000 sq ft; anything else is a misread number ("2 size", "50000 size").
    for field in ("size", "size_min", "size_max"):
        if getattr(criteria, field) is not None and not 150 <= getattr(criteria, field) <= 20000:
            setattr(criteria, field, None)
    criteria.carpet = criteria.has_size() and "carpet" in lowered


def _parse_budget(lowered, criteria):
    if match := re.search(rf"(?:between\s+{_NUM}\s*(?:{_MONEY_UNIT})?\s*and|{_NUM}\s*(?:{_MONEY_UNIT})?\s*(?:-|to))\s*{_NUM}\s*{_MONEY_UNIT}",
                          lowered):
        number, unit = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        criteria.budget_min = _amount(number, unit or match.group(6))
        criteria.budget_max = _amount(match.group(5), match.group(6))
    elif match := re.search(rf"{_MORE}\s*(?:₹|rs\.?|inr)?\s*{_NUM}\s*{_MONEY_UNIT}", lowered):
        criteria.budget_min = _amount(match.group(1), match.group(2))
    elif match := re.search(rf"(?:₹|rs\.?|inr)?\s*{_NUM}\s*{_MONEY_UNIT}", lowered):
        criteria.budget_max = _amount(match.group(1), match.group(2))
    elif match := re.search(r"(?:₹|rs\.?|inr)\s*(\d{6,10})\b", lowered) or re.search(
            r"\b(?:budget|price|under|upto|up to|below)\s*(?:of\s*|is\s*)?(?:₹|rs\.?)?\s*(\d{6,10})\b", lowered):
        criteria.budget_max = float(match.group(1))  # "₹45,00,000" / "budget 4500000": already rupees
    elif match := re.search(r"\bbudget\s*(?:of\s*|is\s*)?(\d{1,3})\b(?!\s*(?:bhk|rk|sq|%))", lowered):
        criteria.budget_max = float(match.group(1)) * 1e5  # "budget 60" means 60 lakh
    # A home costs ₹2 lakh to ₹50 crore; anything else is a misread number.
    for field in ("budget_min", "budget_max"):
        if getattr(criteria, field) is not None and not 2e5 <= getattr(criteria, field) <= 5e8:
            setattr(criteria, field, None)
    if criteria.budget_min and criteria.budget_max and criteria.budget_min > criteria.budget_max:
        criteria.budget_min, criteria.budget_max = criteria.budget_max, criteria.budget_min


def parse_criteria(text, places):
    """Search criteria from the customer's message, tolerating typos, number words, Indian number formats,
    size units and phrasing ("above 1200 sq ft", "800-1000 carpet", "1.2k sqft", "50,00,000", "Wakad or
    Hinjewadi"). `places` are the cities and localities in our project data."""
    lowered = _normalise(text, places)
    criteria = Criteria()
    criteria.places = _parse_places(lowered, places)
    criteria.place = criteria.places[0] if criteria.places else ""
    kinds = [0.5] if re.search(r"\b1\s*rk\b", lowered) else []
    # "2 or 3 bhk", "2/3 bhk", "2-3 bhk", "2bhk and 3bhk": every number a BHK word applies to.
    for match in re.finditer(r"\b(\d(?:\.5)?)\s*(?:(?:or|/|-|,|and|to|aur|kiva)\s*(\d(?:\.5)?)\s*)?"
                             r"(?:bhk|bedroom|bed\b|b\.h\.k)", lowered):
        kinds += [float(n) for n in match.groups() if n]
    kinds = list(dict.fromkeys(k for k in kinds if 0 < k <= 10))
    criteria.bhks = tuple(kinds)
    criteria.bhk = kinds[0] if kinds else None
    _parse_size(lowered, criteria)
    _parse_budget(lowered, criteria)
    criteria.ready = bool(re.search(r"\bready\b|immediate possession|ready to move|possession now", lowered))
    return criteria


def is_search(text):
    from services.text_fuzz import correct_words
    search_words = {"looking", "property", "properties", "flat", "flats", "apartment", "apartments", "house",
                    "houses", "homes", "budget", "options", "search", "suggest", "ready", "possession"}
    return bool(SEARCH_RE.search(correct_words(str(text or ""), search_words)))


def bhk_of(typology):
    """BHK from typology type/name ("2BHK+T", "1 RK"); None for shops and offices."""
    label = f"{typology.get('typologyType') or ''} {typology.get('typologyName') or ''}".lower()
    if re.search(r"\b1\s*rk\b", label):
        return 0.5
    match = re.search(r"(\d)\s*bhk", label)
    return float(match.group(1)) if match else None


def _possession(wing):
    value = wing.get("expectedPossesionDate")
    return datetime.fromtimestamp(value / 1000).date() if isinstance(value, (int, float)) and value else None


def project_matches(project, wings, typologies_by_wing, available_by_typology, criteria, today=None):
    """Matching homes in one project, summarised for the customer, or None."""
    today = today or date.today()
    homes = []
    for wing in wings:
        possession = _possession(wing)
        ready = (str(wing.get("constructionStatus") or "").lower().startswith("ready")
                 or (possession is not None and possession <= today))
        if criteria.ready and not ready:
            continue
        for typology in typologies_by_wing.get(wing.get("id"), []):
            bhk, area = bhk_of(typology), typology.get("saleableArea")
            rate_min, rate_max = typology.get("minBasePrice"), typology.get("maxBasePrice")
            available = available_by_typology.get((wing.get("id"), typology.get("id")), 0)
            if bhk is None or not area or not available:
                continue  # shops, missing size, or nothing left to sell
            wanted = criteria.bhks or ((criteria.bhk,) if criteria.bhk is not None else ())
            if wanted and bhk not in wanted:
                continue
            measured = (typology.get("carpetArea") or 0) if criteria.carpet else area
            if criteria.size and abs(measured - criteria.size) > criteria.size * SIZE_TOLERANCE:
                continue
            if (criteria.size_min and measured < criteria.size_min) or (criteria.size_max and measured > criteria.size_max):
                continue
            price_min = area * rate_min if rate_min else None
            price_max = area * (rate_max or rate_min) if rate_min else None
            if criteria.budget_max and (price_min is None or price_min > criteria.budget_max):
                continue
            if criteria.budget_min and price_max is not None and price_max < criteria.budget_min:
                continue
            homes.append({"bhk": bhk, "area": area, "price_min": price_min, "price_max": price_max,
                          "available": available, "possession": possession, "ready": ready})
    if not homes:
        return None
    prices = [h["price_min"] for h in homes if h["price_min"]] + [h["price_max"] for h in homes if h["price_max"]]
    possessions = [h["possession"] for h in homes if h["possession"]]
    return {
        "name": str(project.get("projectName", "")).strip(),
        "place": ", ".join(p for p in (project.get("locality"), project.get("city")) if p),
        "bhks": sorted({h["bhk"] for h in homes}),
        "area_min": min(h["area"] for h in homes), "area_max": max(h["area"] for h in homes),
        "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
        "available": sum(h["available"] for h in homes),
        "possession": min(possessions) if possessions else None,
        "ready": any(h["ready"] for h in homes),
    }


def describe_match(match, budget_set=False):
    """One line per project. With a budget, the price is "from" the cheapest match (the top of the range
    can exceed the budget on higher floors / rates)."""
    bhks = ", ".join("1 RK" if b == 0.5 else f"{b:g}BHK" for b in match["bhks"])
    size = (f"{match['area_min']:,.0f} sq ft" if match["area_min"] == match["area_max"]
            else f"{match['area_min']:,.0f}-{match['area_max']:,.0f} sq ft")
    price = ""
    if match["price_min"]:
        low, high = lakhs(match["price_min"]), lakhs(match["price_max"])
        # The API's rate ranges can span 2x; a range that wide says nothing, so show where prices start.
        wide = match["price_max"] >= match["price_min"] * WIDE_PRICE_RATIO
        price = (f", from approx. {low}" if budget_set or wide
                 else f", approx. {low}" + ("" if low == high else f" - {high}"))
    when = "ready to move" if match["ready"] else (
        f"possession {match['possession']:%b %Y}" if match["possession"] else "")
    place = f" ({match['place']})" if match["place"] else ""
    return (f"{match['name']}{place}: {bhks}, {size}{price}"
            + (f", {when}" if when else "") + f", {match['available']} listed")


def project_summary(project, wings, typologies_by_wing, available_by_typology, bhk=None, today=None,
                    fields=("size", "carpet", "price", "listed")):
    """One project's homes for a buyer: each wing (floors, possession, flats left) and each BHK type
    (saleable and carpet area, approx. price, flats left). Shops are left out. `bhk` is one BHK or a
    collection of them ("2 and 3 BHK details"). `fields` picks what each BHK line shows, so an answer
    carries only what was asked ("price of Prime" needs no carpet areas)."""
    today = today or date.today()
    wanted_bhks = set(bhk) if isinstance(bhk, (set, tuple, list)) else ({bhk} if bhk is not None else set())
    wing_lines, by_bhk = [], {}
    for wing in wings:
        possession = _possession(wing)
        typologies = typologies_by_wing.get(wing.get("id"), [])
        left = sum(available_by_typology.get((wing.get("id"), t.get("id")), 0) for t in typologies if bhk_of(t) is not None)
        ready = str(wing.get("constructionStatus") or "").lower().startswith("ready") or (
            possession is not None and possession <= today)
        details = [f"{wing['totalFloors']} floors" if wing.get("totalFloors") else "",
                   "ready to move" if ready else (f"possession {possession:%b %Y}" if possession else ""),
                   f"{left} flats listed"]
        wing_lines.append(f"{str(wing.get('name') or 'Wing').strip()} ({', '.join(d for d in details if d)})")
        for typology in typologies:
            kind = bhk_of(typology)
            if kind is None or (wanted_bhks and kind not in wanted_bhks):
                continue
            entry = by_bhk.setdefault(kind, {"areas": [], "carpets": [], "prices": [], "available": 0})
            if typology.get("saleableArea"):
                entry["areas"].append(typology["saleableArea"])
                for rate in (typology.get("minBasePrice"), typology.get("maxBasePrice")):
                    if rate:
                        entry["prices"].append(typology["saleableArea"] * rate)
            if typology.get("carpetArea"):
                entry["carpets"].append(typology["carpetArea"])
            entry["available"] += available_by_typology.get((wing.get("id"), typology.get("id")), 0)

    def span(values, fmt):
        low, high = fmt(min(values)), fmt(max(values))
        return low if low == high else f"{low} - {high}"

    home_lines = []
    for kind in sorted(by_bhk):
        entry = by_bhk[kind]
        parts = ["1 RK" if kind == 0.5 else f"{kind:g}BHK"]
        if entry["areas"] and "size" in fields:
            parts.append(span(entry["areas"], lambda v: f"{v:,.0f}") + " sq ft")
            if entry["carpets"] and "carpet" in fields:
                parts[-1] += f" (carpet {span(entry['carpets'], lambda v: f'{v:,.0f}')} sq ft)"
        if entry["prices"] and "price" in fields:
            low, high = min(entry["prices"]), max(entry["prices"])
            parts.append(f"from approx. {lakhs(low)}" if high >= low * WIDE_PRICE_RATIO
                         else "approx. " + span(entry["prices"], lakhs))
        if "listed" in fields:
            parts.append(f"{entry['available']} listed")
        home_lines.append(", ".join(parts))
    return wing_lines, home_lines


def project_in_place(project, place):
    if not place:
        return True
    fields = " ".join(str(project.get(k) or "") for k in ("city", "locality", "address", "location")).lower()
    return bool(re.search(rf"\b{re.escape(place)}\b", fields))


def relaxations(criteria):
    """Looser searches to try, in order, when nothing fits: size, then budget, then readiness, then BHK.
    The place is never dropped: a buyer in Pune doesn't want Thane."""
    loosened = Criteria(**vars(criteria))
    steps = []
    groups = ((("size", "size_min", "size_max"), "size"), (("budget_max", "budget_min"), "budget"),
              (("ready",), "ready to move"), (("bhk", "bhks"), "BHK"))
    for fields, label in groups:
        if any(getattr(loosened, f) for f in fields):
            for f in fields:
                setattr(loosened, f, False if f == "ready" else () if f == "bhks" else None)
            steps.append((label, Criteria(**vars(loosened))))
    return steps
