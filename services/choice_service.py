"""Quick-reply buttons for chat answers, so customers pick instead of typing.

Choice shape: {"label", "value", "action"?}. Without an action the widget sends
`value` as the customer's next message; "project" opens the widget's guided
project -> wing -> floor -> flat explorer for the project named in `value`.
"""
import re

QUESTION_PROJECT_RE = re.compile(r"which (?:of (?:our|the) )?(?:\d+ )?projects?|project name|name of the project", re.IGNORECASE)


def project_choice(name):
    return {"label": name, "value": name, "action": "project"}


def project_choices(names):
    return [project_choice(name) for name in names]


# Next-step topics for one project; the regex spots the topic the customer just asked about.
PROJECT_TOPICS = (
    ("explore", "Explore homes", "{name}", re.compile(r"\b(homes?|flats?|units?|inventory|availab)", re.I)),
    ("location", "Location", "Where is {name} located?", re.compile(r"\b(where|locat|address|kuthe|kahan)", re.I)),
    ("prices", "Prices", "What are the prices at {name}?", re.compile(r"\b(price|pricing|rate|cost|kimat)", re.I)),
    ("amenities", "Amenities", "What amenities does {name} have?", re.compile(r"\b(amenit|facilit)", re.I)),
    ("offers", "Offers", "What offers are available at {name}?", re.compile(r"\b(offer|discount|scheme|deal)", re.I)),
    ("payment plan", "Payment plan", "What is the payment plan at {name}?",
     re.compile(r"\b(payment|instal|milestone|booking amount)", re.I)),
    ("book", "Book a site visit", "Book a site visit at {name}", re.compile(r"\b(book\b|site visit)", re.I)),
)


def single_project_choices(name, skip="", question=""):
    """Next steps for one project, leaving out the topic just answered (by key, or spotted in the question)."""
    choices = []
    for key, label, value, asked in PROJECT_TOPICS:
        if key == skip or (question and key != "explore" and asked.search(question)):
            continue
        choice = {"label": label, "value": value.format(name=name)}
        if key == "explore":
            choice["action"] = "project"
        choices.append(choice)
    return choices


def mentioned_projects(text, project_names):
    """Live project names in `text`, in order of appearance; longest name wins ("Empire NX" is not also "Empire")."""
    remaining, found = str(text or ""), []
    for name in sorted({n for n in project_names if n}, key=len, reverse=True):
        pattern = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])", re.IGNORECASE)
        match = pattern.search(remaining)
        if match:
            found.append((match.start(), name))
            remaining = pattern.sub(" " * len(name), remaining)
    return [name for _, name in sorted(found)]


def choices_for_answer(payload, project_names, question=""):
    """Buttons for a property answer that has none: the projects it lists, next steps for the one project it
    is about (minus the topic `question` asked), or every project when it asks the customer to pick one."""
    if payload.get("choices") or payload.get("route") != "property" or payload.get("handoff_recommended"):
        return payload.get("choices") or []
    answer = str(payload.get("answer", ""))
    asked_about = mentioned_projects(question, project_names)
    if len(asked_about) == 1:
        # The question picks the project; other names in the answer are incidental ("NX: Vishwajeet Empire, ..." address).
        return single_project_choices(asked_about[0], question=question)
    named = mentioned_projects(answer, project_names)
    if len(named) >= 2:
        return project_choices(named)
    if len(named) == 1:
        return single_project_choices(named[0], question=question)
    if QUESTION_PROJECT_RE.search(answer):
        return project_choices(project_names)
    return []
