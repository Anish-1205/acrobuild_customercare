"""Reply-language helpers shared by the orchestrator and the property answer path.

Heuristic detection here is only a fallback for when the LLM turn analyzer
(services.turn_analysis_service) is unavailable. The romanized lexicons mirror
src/lib/chatLanguage.ts — keep the two in sync.
"""
import re

ENGLISH = "English"

# Native Unicode scripts -> language. Devanagari is also used by Marathi; disambiguated
# below using Marathi-distinctive words, since without that Hindi is the more likely reading.
_SCRIPT_LANGUAGES = (
    (re.compile(r"[ঀ-৿]"), "Bengali"),
    (re.compile(r"[ऀ-ॿ]"), "Hindi"),
    (re.compile(r"[਀-੿]"), "Punjabi"),
    (re.compile(r"[઀-૿]"), "Gujarati"),
    (re.compile(r"[଀-୿]"), "Odia"),
    (re.compile(r"[஀-௿]"), "Tamil"),
    (re.compile(r"[ఀ-౿]"), "Telugu"),
    (re.compile(r"[ಀ-೿]"), "Kannada"),
    (re.compile(r"[ഀ-ൿ]"), "Malayalam"),
    (re.compile(r"[؀-ۿ]"), "Urdu"),
)

# Distinctive words of Indian languages as typed in English letters. Order matters
# for tie-breaks (earlier wins).
ROMANIZED_LEXICONS = {
    "Hindi": frozenset("""
        hai hain kya kyun kaise kaisa kaisi kahan kab kaun kaunsa konsa konse kaunse mujhe mera
        meri mere aap aapka aapke aapko apke tum tumhara nahi nahin haan chahiye batao bataiye
        dikhao dikhaiye kijiye kitna kitne kitni ghar bhai accha acha theek thik samajh boliye
        mein raha rahi rahe hoga sakte sakta wala wali wale paas liye abhi kuch bahut kripya
    """.split()),
    "Telugu": frozenset("""
        enti emiti emi ela elaa unnava unnaru unnayi unnaya naku naaku meeku miku kavali kaavali
        cheppu cheppandi avunu ledu levu enduku eppudu ekkada bagunnara bagunnava namaskaram
        cheddam chedham chedama cheyandi chupinchu chupinchandi manam entha illu evi kosam
        vaccha vacha vachu vacchu telusu telidu peru nenu nuvvu meeru ayindi undi ivvandi
        matladu matladandi evaru nee em
    """.split()),
    "Tamil": frozenset("""
        enna yenna epdi eppadi enga engae yaar yaaru evvalavu evlo sollu sollunga irukku irukka
        iruku irukkinga venum vendum panren pandre panra panringa pannunga naan neenga unga ungal
        enakku ungalukku illai aama vanakkam romba nalla theriyuma theriyum pesu pesunga peyar
        kaatu kaatunga veedu
    """.split()),
    "Kannada": frozenset("""
        enu yenu hege hegiddira hegiddiya elli yelli beku bekagide helu heli nimma nimge nanna
        nange naanu neevu ide idhe yaava yavdu thorisi torisi eshtu estu maadi banni gottilla
        gottu hesaru chennagi namaskara
    """.split()),
    "Malayalam": frozenset("""
        enthu enthanu evide engane venam vendi parayu parayoo ningal ningalude ente enikku
        kanikku ethra sugamano sukhamano alle aano aanu cheyyam pinne
    """.split()),
    "Marathi": frozenset("""
        aahe ahe aahet kay kasa kashi kase kuthe kuthla kuthle konte mala tumhi tumhala amhi
        pahije madhe madhye bola sanga dakhva dakhava kiti nako kaay jhala zala
    """.split()),
    "Bengali": frozenset("""
        achhe acho achen ami amar tumi tomar apni apnar koto kothay kothae dekhao bolo bolun
        lagbe nei kemon bhalo korbo koro korun dhonnobad
    """.split()),
    "Gujarati": frozenset("""
        che chhe cho shu shun tamne tamaru joie joiye kem batavo ketla ketlu nathi saru
        majama avjo
    """.split()),
    "Punjabi": frozenset("""
        tusi tuhanu sanu chahida kiddan kithe dasso kinne kinna haige naal vich
    """.split()),
}

_LANGUAGE_NAME_ALIASES = {
    "english": ENGLISH, "hindi": "Hindi", "hinglish": "Hindi", "telugu": "Telugu",
    "tenglish": "Telugu", "tamil": "Tamil", "tanglish": "Tamil", "kannada": "Kannada",
    "malayalam": "Malayalam", "marathi": "Marathi", "bengali": "Bengali", "bangla": "Bengali",
    "gujarati": "Gujarati", "punjabi": "Punjabi", "odia": "Odia", "oriya": "Odia",
    "urdu": "Urdu", "assamese": "Assamese",
}

_COMMON_ENGLISH_WORDS = frozenset("""
    a about after all also am an and any anything are as ask at available be because been best
    between book but buy by can could cost day did do does doing done each even ever find flat
    flats floor for from get give go going good had has have he hello help her here hi his home
    how i if in into is it its just know let like list live looking make many me more most much
    my name need new no not now of off ok okay on one only or other our out over please price
    project projects property rate right say see she should show so some sure tell than thank
    thanks that the their them then there these they thing think this those time to today too
    up us visit want was way we well were what when where which who whom whose why will with
    would yes you your
""".split())

_TOKEN_RE = re.compile(r"[a-z]+")
_DEVANAGARI_WORD_RE = re.compile(r"[ऀ-ॿ]+")

# Devanagari words distinctive of Marathi (not shared with standard Hindi), so a
# native-script Marathi message isn't misread as Hindi ("ठाण्यात तुमच्या कोणत्या
# मालमत्ता आहेत?" answered in Hindi instead of Marathi).
_MARATHI_DEVANAGARI_MARKERS = frozenset("""
    आहे आहेत अहे आहात कसा कशी कसे कुठे कुठला कुठली कुठले कोणता कोणती कोणते
    मला तुम्ही तुम्हाला आम्हाला आम्ही माझ्या तुमच्या पाहिजे मध्ये बोला सांगा
    दाखवा किती नको झाला झाली झालं मराठी मालमत्ता नाही
""".split())


def canonical_language(value):
    cleaned = str(value or "").strip().lower()
    if not cleaned:
        return ""
    return _LANGUAGE_NAME_ALIASES.get(cleaned, cleaned[:1].upper() + cleaned[1:])


def detect_script_language(text):
    text = str(text or "")
    for pattern, language in _SCRIPT_LANGUAGES:
        if pattern.search(text):
            if language == "Hindi" and set(_DEVANAGARI_WORD_RE.findall(text)) & _MARATHI_DEVANAGARI_MARKERS:
                return "Marathi"
            return language
    return ""


def guess_romanized_language(text):
    words = _TOKEN_RE.findall(str(text or "").lower())
    scores = {
        language: sum(1 for word in words if word in lexicon)
        for language, lexicon in ROMANIZED_LEXICONS.items()
    }
    best = max(scores.values(), default=0)
    if not best:
        return ""
    return next(language for language, score in scores.items() if score == best)


def requested_language(text):
    """A language named explicitly in the message ("telugu lo cheppu", "reply in tamil")."""
    names = {
        _LANGUAGE_NAME_ALIASES[word]
        for word in _TOKEN_RE.findall(str(text or "").lower())
        if word in _LANGUAGE_NAME_ALIASES
    }
    return names.pop() if len(names) == 1 else ""


def looks_confidently_english(text):
    words = _TOKEN_RE.findall(str(text or "").lower().replace("'s", ""))
    if not words or detect_script_language(text) or guess_romanized_language(text):
        return False
    return sum(1 for word in words if word in _COMMON_ENGLISH_WORDS) / len(words) >= 0.5


_LANGUAGE_NEUTRAL_WORDS = frozenset("""
    ok okay k kk yes no yeah yep nope hmm hm haan ha thanks thank thx ty sure fine done cool great nice
""".split())


def has_no_language_of_its_own(text):
    """Acks, numbers and emojis ("ok", "3", "👍") should keep the conversation's language."""
    words = _TOKEN_RE.findall(str(text or "").lower())
    return not detect_script_language(text) and all(word in _LANGUAGE_NEUTRAL_WORDS for word in words)


def strong_reply_language(text):
    """A language the message itself makes unmistakable, or "". Used to overrule the
    LLM analyzer when it lets an earlier conversation language stick."""
    script_language = detect_script_language(text)
    if script_language:
        return script_language
    explicit = requested_language(text)
    if explicit:
        return explicit
    words = _TOKEN_RE.findall(str(text or "").lower().replace("'s", ""))
    romanized = guess_romanized_language(text)
    if romanized:
        hits = sum(1 for word in words if word in ROMANIZED_LEXICONS[romanized])
        return romanized if hits >= 2 else ""
    if len(words) >= 3 and looks_confidently_english(text):
        return ENGLISH
    return ""


def heuristic_reply_language(text, previous_language=""):
    """Returns (language, script) or ("", "") when nothing is confidently detectable."""
    script_language = detect_script_language(text)
    if script_language:
        return script_language, "native"
    explicit = requested_language(text)
    if explicit:
        return explicit, "latin"
    romanized = guess_romanized_language(text)
    if romanized:
        return romanized, "latin"
    if looks_confidently_english(text):
        return ENGLISH, "latin"
    if previous_language:
        return previous_language, "latin"
    return "", ""


_DIRECTIVE_RE = re.compile(r"\s*\[Reply language:[^\]]*\]\s*$")


def build_reply_language_directive(language, script="latin"):
    """Phrased without "in <X>" so the property answer parser can't read the language
    name as a location (that produced "No projects in English")."""
    language = canonical_language(language)
    if not language:
        return (
            "\n\n[Reply language: same as the customer's latest message, matching their "
            "script and style]"
        )
    if language == ENGLISH:
        return "\n\n[Reply language: English]"
    if script == "native":
        return f"\n\n[Reply language: {language}, using {language} script]"
    return (
        f"\n\n[Reply language: {language}, romanized with English letters the way the customer "
        f"types; not English, not {language} script]"
    )


def strip_reply_language_directive(text):
    return _DIRECTIVE_RE.sub("", str(text or ""))
