"""Several requests in one chat message: "price of Prime and amenities of Paradise", "where is Heights? any
offers?", "price of Prime and Paradise". Each part is answered on its own by the grounded answers.

The text is the turn's canonical English (services/vocabulary.py), so one word per topic is enough here. A
message only splits where both sides ask something different (another topic or another project): "2bhk
and 3bhk in Pune" or "parking and lift" are one request and stay whole.
"""
import re

_TOPICS = {
    "price": r"\bprice\b",
    "amenities": r"\bamenities\b",
    "location": r"\b(location|where)\b",
    "offers": r"\boffers\b",
    "payment plan": r"\bpayment plan\b",
    "possession": r"\bpossession\b",
    "rera": r"\brera\b",
    "contact": r"\bcontact\b",
    "floor": r"\bfloors?\b",
    "size": r"\b(size|sq ?ft)\b",
    "wing": r"\bwings?\b",
}
_SENTENCE_RE = re.compile(r"\?+|;|\n")
_AND_RE = re.compile(r"\s*,?\s+(?:and also|and|also|plus|aur bhi|aur|ani|saath hi|&)\s+", re.IGNORECASE)
MAX_PARTS = 4


def topics(text):
    return {name for name, pattern in _TOPICS.items() if re.search(pattern, text, re.IGNORECASE)}


def split_requests(text, find_project):
    """The separate requests in `text`, each able to stand alone, or [text] when it is one request.
    `find_project(text)` returns the project name a piece names, or None."""
    pieces = []
    for sentence in _SENTENCE_RE.split(str(text or "")):
        sentence = sentence.strip(" ,.!")
        if not sentence:
            continue
        if pieces and not topics(sentence) and find_project(sentence) is None:
            pieces[-1] = f"{pieces[-1]} {sentence}"  # "3bhk in Pune? with gym" is still one search
            continue
        pieces += _split_on_and(sentence, find_project)
    if len(pieces) > 1 and not topics(pieces[0]) and find_project(pieces[0]) is None:
        pieces[1] = f"{pieces[0]} {pieces[1]}"  # "hi? price of Prime": the greeting is not a request
        pieces.pop(0)
    if len(pieces) < 2:
        return [str(text or "").strip()]
    # "price and amenities of Prime": a piece naming no project takes the project named next to it.
    named = [find_project(piece) for piece in pieces]
    for index, piece in enumerate(pieces):
        if named[index] is None and topics(piece):
            nearby = next((named[j] for j in (index - 1, index + 1) if 0 <= j < len(pieces) and named[j]), None)
            if nearby:
                pieces[index] = f"{piece} of {nearby}"
    return pieces[:MAX_PARTS]


def _split_on_and(sentence, find_project):
    parts = _AND_RE.split(sentence)
    merged = [parts[0]]
    for part in parts[1:]:
        current = merged[-1]
        current_project, part_project = find_project(current), find_project(part)
        if topics(part) and topics(current) and (topics(part) != topics(current) or
                                                 (part_project and part_project != current_project)):
            merged.append(part)  # another question: "price of Prime" + "amenities of Paradise"
        elif (not topics(part) and part_project and current_project and part_project != current_project
              and topics(current) and len(part.split()) <= 4):
            # "price of Prime and Paradise": the same question about another project.
            merged.append(re.sub(re.escape(_mention(current, current_project)), part, current, flags=re.IGNORECASE))
        else:
            merged[-1] = f"{current} and {part}"
    return merged


def _mention(text, project):
    """How `text` refers to `project` ("prime" for "Vishwajeet Prime"): the longest piece of the name it uses."""
    words = project.split()
    for size in range(len(words), 0, -1):
        for start in range(len(words) - size + 1):
            phrase = " ".join(words[start:start + size])
            if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
                return phrase
    return project
