"""One shared vocabulary for the words Indian buyers use for the same thing.

Every turn's English rendering goes through `canonicalize` before routing, so each answer only needs
to understand the canonical word: "features" / "suvidha" -> "amenities", "block" / "building" -> "wing",
"cost" / "kimat" -> "price", "carpet area" / "built-up" -> "size", "kahan" / "kuthe" -> "location".
The turn analyzer is told to use the same canonical words (see turn_analysis_service).
"""
import re

# canonical word -> synonyms (whole words or phrases, case-insensitive). Longest phrases are applied first.
SYNONYMS = {
    "amenities": (
        "features", "feature", "facilities", "facility", "functionalities", "functionality", "specifications",
        "specification", "specs", "highlights", "utilities", "services offered", "suvidha", "suvidhaye",
        "suvidhayen", "suvidhaen", "sukh suvidha", "sukh-suvidha", "soyi", "soyee", "sahuliyat",
    ),
    "price": (
        "cost", "costs", "costing", "amount", "rates", "rate", "pricing", "prices", "charges",
        "kimat", "kimmat", "keemat", "kimath", "daam", "bhav", "bhaav", "how much",
        "price list", "rate card", "rate list", "cost sheet", "quotation", "quote", "valuation", "kitne ka",
        "kitne ki", "kitne mein", "kitna padega", "kitne me", "dhara", "dharalu", "vilai", "bele", "kimmath",
        "per sq ft rate", "per sqft rate", "base price", "all inclusive",
    ),
    "floor": ("storey", "storeys", "stories", "manzil", "manzile", "maala", "majla", "majle", "antastu"),
    "rera": ("maharera", "rera number", "rera no", "rera registration", "registration number", "reg no"),
    "ready to move": ("ready possession", "ready-possession", "ready to occupy", "rtm", "immediate possession",
                      "move in ready", "ready flat", "ready flats", "tayyar", "taiyar", "tayar"),
    "contact": ("phone number", "mobile number", "contact number", "helpline number", "whatsapp number",
                "call you", "sampark"),
    "wing": (
        "wings", "block", "blocks", "building", "buildings", "tower", "towers", "phase", "phases", "imarat",
        "imaarat", "building no",
    ),
    "flat": (
        "unit", "units", "apartment", "apartments", "ghar", "makan", "makaan", "sadnika", "residence",
        "house", "houses",
    ),
    "size": (
        "carpet area", "built up area", "built-up area", "builtup area", "super built up", "super built-up",
        "super area", "saleable area", "salable area", "square footage", "how big", "dimensions",
    ),
    "location": (
        "address", "kahan", "kahaan", "kidhar", "kuthe", "kuthay", "kothe", "ekkada", "enga", "evide",
        "landmark", "locality", "located",
    ),
    "possession": ("handover", "hand over", "completion", "ready by", "move in", "move-in", "kab milega",
                   "possession date", "delivery date", "handing over", "kab tak ready", "kab ready"),
    "offers": ("discounts", "discount", "schemes", "scheme", "deals", "deal", "cashback", "freebies", "ofer",
               "promotion", "promotions", "festive offer", "stamp duty waiver", "chhoot", "chhut", "sut"),
    "payment plan": ("booking amount", "installments", "instalments", "installment", "instalment", "kist", "hapta", "emi plan",
                     "payment schedule", "payment terms", "payment structure", "token amount", "payment breakup",
                     "clp", "slab wise payment", "payment milestones"),
    "site visit": ("dekhne aana", "dekhne aaye", "bhet dena", "property visit", "visit the site"),
}

# Customer words for each amenity, keyed by the words of the CS API's amenity name (its 43 names as of
# 2026-10-29). The amenity matcher adds the key's words when a synonym appears, so "tarantal", "bijli backup"
# or "wifi" find "Swimming Pool", "Power Backup Lift" and "Internet". Plain words that already appear in an
# amenity name ("gym", "lift", "parking") need no entry.
AMENITY_SYNONYMS = {
    "swimming pool": ("pool", "swim", "swimming", "tarantal", "taran tal", "swiming", "swimmimg"),
    "baby swimming": ("baby pool", "kids pool", "kiddie pool", "children pool", "toddler pool"),
    "gym": ("gymnasium", "fitness", "fitness centre", "fitness center", "health club", "workout", "exercise",
            "vyayamshala", "vyayam"),
    "community house": ("clubhouse", "club house", "club", "community hall", "society hall", "society office"),
    "multipurpose hall": ("banquet", "function hall", "event hall", "hall", "auditorium"),
    "party lawn": ("party", "party area", "celebration area", "lawn", "open lawn"),
    "park": ("garden", "gardens", "greenery", "green area", "green space", "bagicha", "bageecha",
             "udyan", "landscape", "landscaping"),
    "children playing": ("kids", "kid", "child", "children", "play", "play area", "playground", "play ground", "khel",
                         "bachche", "bacche", "bachon", "bacchon", "tot lot"),
    "lift": ("elevator", "elevators", "lifts"),
    "cctv coverage": ("cctv", "camera", "cameras", "surveillance"),
    "security personnel": ("security", "guard", "guards", "watchman", "chowkidar", "security guard", "suraksha"),
    "gated community": ("gated", "gated society", "compound wall", "boundary wall"),
    "jogging track": ("jogging", "walking track", "running track"),
    "paved walkway": ("walkway", "pathway", "footpath"),
    "yoga meditation": ("yoga", "meditation", "dhyan", "dhyana"),
    "24x7 water supply": ("water", "24 hour water", "24x7 water", "paani", "pani", "water supply"),
    "24x7 electricity supply": ("electricity", "bijli", "power supply", "24 hour power", "24x7 power"),
    "power backup lift": ("backup", "power backup", "generator", "dg set", "dg backup", "inverter", "bijli backup"),
    "visitor parking": ("visitor parking", "guest parking", "visitors parking"),
    "parking": ("car parking", "car park", "garage", "gaadi", "gadi", "covered parking", "stilt parking",
                "two wheeler parking", "bike parking"),
    "gas pipe": ("gas", "piped gas", "gas line", "gas pipeline"),
    "internet": ("wifi", "wi-fi", "broadband", "fibre", "fiber"),
    "telecom connection": ("telephone", "landline", "mobile network"),
    "solar water heater": ("solar", "solar heater", "geyser"),
    "rain water harvesting": ("rainwater", "rain water", "rwh"),
    "sewage water treatment": ("stp", "sewage", "sewage treatment"),
    "waste management system": ("garbage", "waste", "kachra", "kachara", "garbage disposal"),
    "fire alarm fire fighting tools ready": ("fire safety", "fire", "fire fighting", "sprinkler", "sprinklers"),
    "earthquake resistant": ("earthquake", "seismic", "bhukamp", "bhookamp"),
    "senior citizen friendly": ("senior citizen", "senior citizens", "elderly", "old age", "bujurg", "buzurg"),
    "table tennis court": ("table tennis", "ping pong"),
    "football ground": ("football", "soccer", "sports ground", "playing field"),
    "pool billiards": ("billiards", "billiard", "snooker", "billards"),
    "street lamps": ("street light", "street lights", "streetlight", "street lighting"),
    "acupressure park": ("acupressure",),
    "entrance lobby": ("lobby",),
    "terrace": ("chhat", "chhath", "chat garden", "rooftop", "roof top"),
}


def amenity_expansion(text):
    """`text` with every amenity synonym replaced by the amenity-name words ("tarantal" -> "swimming pool")."""
    lowered = str(text or "").lower()
    billiards = re.search(r"\b(billiards?|billards|snooker)\b", lowered)  # "pool" is then the game
    found = []
    # Longest phrase first, blanked once matched: "kids pool" is the baby pool, not also "pool" and "kids".
    pairs = sorted(((s, words) for words, synonyms in AMENITY_SYNONYMS.items() for s in synonyms),
                   key=lambda pair: len(pair[0]), reverse=True)
    for synonym, words in pairs:
        if billiards and words == "swimming pool":
            continue
        lowered, count = re.subn(rf"(?<![\w-]){re.escape(synonym)}(?![\w-])", " ", lowered)
        if count and words not in found:
            found.append(words)
    return " ".join([lowered.strip()] + found)


def amenities_named(text):
    """The amenities `text` names, as amenity-name keys ("tarantal wala flat" -> {"swimming pool"})."""
    expanded = amenity_expansion(text)
    return {key for key in list(AMENITY_SYNONYMS) + ["gym", "lift", "parking", "terrace", "badminton", "carrom",
                                                      "internet", "maintenance", "lawn"]
            if re.search(rf"\b{re.escape(key)}\b", expanded)}


# Words that may name an amenity: only these trigger the (one call per project) amenity lookup. Generic
# words from amenity names ("ready", "house", "track", "system") are left out on purpose.
AMENITY_TERMS = sorted({s for synonyms in AMENITY_SYNONYMS.values() for s in synonyms} | {
    "amenities", "amenity", "facilities", "facility", "lift", "parking", "gym", "terrace", "badminton",
    "carrom", "internet", "maintenance", "swimming", "harvesting", "billiards", "lawn", "cctv", "community house"})
# Amenity names containing a word the general vocabulary would rewrite ("house" -> "flat").
PROTECTED_PHRASES = ("community house", "club house", "farm house")

_PATTERN = re.compile(
    r"(?<![\w-])(" + "|".join(sorted(
        (re.escape(s) for synonyms in SYNONYMS.values() for s in synonyms), key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)
_CANONICAL = {s.lower(): canonical for canonical, synonyms in SYNONYMS.items() for s in synonyms}


def canonicalize(text, protected=()):
    """Replace synonyms with their canonical word, leaving `protected` phrases (project names such as
    "Metro City Towers") untouched."""
    text = str(text or "")
    masks = {}
    protected = tuple(protected) + PROTECTED_PHRASES
    for index, phrase in enumerate(sorted((p for p in protected if p), key=len, reverse=True)):
        token = f"\x00{index}\x00"
        text, count = re.subn(re.escape(phrase), token, text, flags=re.IGNORECASE)
        if count:
            masks[token] = phrase
    text = _PATTERN.sub(lambda m: _CANONICAL[m.group(1).lower()], text)
    for token, phrase in masks.items():
        text = text.replace(token, phrase)
    return text


def mentions(text, canonical):
    """Whether `text` asks about `canonical`, by the word itself or any synonym."""
    return bool(re.search(rf"\b{re.escape(canonical)}\b", canonicalize(text), re.IGNORECASE))
