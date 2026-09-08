import os
from datetime import datetime
from zoneinfo import ZoneInfo

from services.admin_settings_service import (
    get_business_hours_label,
)

DEFAULT_BRAND_TAG = os.getenv(
    "SUPPORT_DEFAULT_BRAND",
    "Acrobuild",
).strip() or "Acrobuild"

SUPPORT_TIMEZONE = os.getenv(
    "SUPPORT_TIMEZONE",
    "Asia/Kolkata",
).strip() or "Asia/Kolkata"

BUSINESS_HOURS_START = int(
    os.getenv(
        "SUPPORT_BUSINESS_HOURS_START",
        "9",
    )
)

BUSINESS_HOURS_END = int(
    os.getenv(
        "SUPPORT_BUSINESS_HOURS_END",
        "19",
    )
)

AGENT_DIRECTORY = {
    "Agent Priya": {
        "team": "Sales Advisory",
        "specialties": [
            "Sales",
            "Quotation Request",
            "Availability Check",
        ],
    },
    "Agent Omar": {
        "team": "Project Finance",
        "specialties": [
            "Payments",
            "Payment Plan",
            "Refund Review",
        ],
    },
    "Agent Kavya": {
        "team": "Documentation Desk",
        "specialties": [
            "Documentation",
            "Legal Documentation",
            "Account Access",
        ],
    },
    "Agent Arjun": {
        "team": "Site Operations",
        "specialties": [
            "Construction",
            "Site Visit",
            "Construction Update",
        ],
    },
    "Agent Neha": {
        "team": "Handover and Care",
        "specialties": [
            "Handover",
            "Maintenance",
            "Maintenance Request",
        ],
    },
    "Agent Rohan": {
        "team": "Priority Escalations",
        "specialties": [
            "Priority Response",
            "Investor Escalations",
        ],
    },
}

AGENT_OPTIONS = list(
    AGENT_DIRECTORY.keys()
)

STATUS_OPTIONS = [
    "Open",
    "In Progress",
    "Waiting on Customer",
    "Resolved",
    "Closed",
]

BUSINESS_HOURS_OPTIONS = [
    "Business Hours",
    "After Hours",
    "Weekend Coverage",
]

INTENT_FALLBACKS = {
    "Account": "Account Access",
    "Construction": "Construction Update",
    "Documentation": "Legal Documentation",
    "General": "General Inquiry",
    "Handover": "Possession / Handover",
    "Maintenance": "Maintenance Request",
    "Payments": "Payment Plan",
    "Sales": "Quotation Request",
    "Site Visit": "Site Visit Request",
}


# -----------------------------------
# TIME HELPERS
# -----------------------------------

def get_support_timezone():

    try:
        return ZoneInfo(
            SUPPORT_TIMEZONE
        )

    except Exception:
        return ZoneInfo("UTC")


def get_support_now():

    return datetime.now(
        get_support_timezone()
    )


def get_ticket_timestamp():

    return get_support_now().isoformat(
        timespec="seconds"
    )


# -----------------------------------
# TAGGING HELPERS
# -----------------------------------

def detect_brand_tag(customer_email=""):

    customer_email = str(
        customer_email or ""
    ).strip().lower()

    if any(
        customer_email.endswith(domain)
        for domain in (
            "@acrobuild.com",
            "@acrobuild.in",
            "@acrobuildrealty.com",
        )
    ):
        return "Acrobuild Internal"

    return DEFAULT_BRAND_TAG


def classify_intent_tag(
    issue,
    issue_type="General",
):

    issue_lower = str(issue or "").lower()

    if any(
        keyword in issue_lower
        for keyword in (
            "refund",
            "cancel booking",
            "chargeback",
            "booking cancellation",
        )
    ):
        return "Refund Review"

    if any(
        keyword in issue_lower
        for keyword in (
            "payment",
            "invoice",
            "receipt",
            "emi",
            "installment",
            "instalment",
            "outstanding",
            "statement",
        )
    ):
        return "Payment Plan"

    if any(
        keyword in issue_lower
        for keyword in (
            "password",
            "login",
            "portal",
            "account",
            "access",
        )
    ):
        return "Account Access"

    if any(
        keyword in issue_lower
        for keyword in (
            "site visit",
            "visit",
            "sample flat",
            "inspection",
            "tour",
            "walkthrough",
        )
    ):
        return "Site Visit Request"

    if any(
        keyword in issue_lower
        for keyword in (
            "progress",
            "construction",
            "milestone",
            "timeline",
            "delay",
            "completion",
        )
    ):
        return "Construction Update"

    if any(
        keyword in issue_lower
        for keyword in (
            "agreement",
            "document",
            "registration",
            "registry",
            "title deed",
            "approval",
            "noc",
            "loan",
            "kyc",
            "legal",
        )
    ):
        return "Legal Documentation"

    if any(
        keyword in issue_lower
        for keyword in (
            "handover",
            "possession",
            "snag",
            "key handover",
            "fitout",
            "fit-out",
        )
    ):
        return "Possession / Handover"

    if any(
        keyword in issue_lower
        for keyword in (
            "maintenance",
            "leak",
            "leakage",
            "seepage",
            "crack",
            "plumbing",
            "electrical",
            "lift",
            "parking",
            "security",
            "repair",
            "defect",
        )
    ):
        return "Maintenance Request"

    if any(
        keyword in issue_lower
        for keyword in (
            "broker",
            "channel partner",
            "partner registration",
        )
    ):
        return "Broker / Channel Partner"

    if any(
        keyword in issue_lower
        for keyword in (
            "quote",
            "quotation",
            "price",
            "pricing",
            "brochure",
        )
    ):
        return "Quotation Request"

    if any(
        keyword in issue_lower
        for keyword in (
            "availability",
            "inventory",
            "unit",
            "project",
            "apartment",
            "villa",
            "plot",
            "commercial",
            "floor plan",
            "booking",
        )
    ):
        return "Availability Check"

    return INTENT_FALLBACKS.get(
        issue_type,
        "General Inquiry",
    )


def get_business_hours_tag(
    reference_time=None,
):

    if reference_time is None:
        reference_time = get_support_now()

    try:
        return get_business_hours_label(
            reference_time
        )

    except Exception:
        if reference_time.weekday() >= 5:
            return "Weekend Coverage"

        if (
            BUSINESS_HOURS_START
            <= reference_time.hour
            < BUSINESS_HOURS_END
        ):
            return "Business Hours"

        return "After Hours"


# -----------------------------------
# ROUTING HELPERS
# -----------------------------------

def get_default_agent(
    issue_type,
    intent_tag,
    customer_context=None,
):

    if customer_context is None:
        customer_context = {}

    if customer_context.get("is_vip"):
        return "Agent Rohan"

    if intent_tag in (
        "Refund Review",
        "Payment Plan",
    ):
        return "Agent Omar"

    if intent_tag in (
        "Account Access",
        "Legal Documentation",
    ):
        return "Agent Kavya"

    if intent_tag in (
        "Site Visit Request",
        "Construction Update",
        "Broker / Channel Partner",
    ):
        return "Agent Arjun"

    if intent_tag in (
        "Possession / Handover",
        "Maintenance Request",
    ):
        return "Agent Neha"

    if intent_tag in (
        "Quotation Request",
        "Availability Check",
    ):
        return "Agent Priya"

    issue_type_map = {
        "Account": "Agent Kavya",
        "Construction": "Agent Arjun",
        "Documentation": "Agent Kavya",
        "General": "Agent Priya",
        "Handover": "Agent Neha",
        "Maintenance": "Agent Neha",
        "Payments": "Agent Omar",
        "Sales": "Agent Priya",
        "Site Visit": "Agent Arjun",
    }

    return issue_type_map.get(
        issue_type,
        "Agent Priya",
    )


def build_queue_name(
    issue_type,
    priority,
    intent_tag,
    customer_context=None,
):

    if customer_context is None:
        customer_context = {}

    if customer_context.get("is_vip"):
        return "Priority Investor Desk"

    if intent_tag in (
        "Refund Review",
        "Payment Plan",
    ):
        return "Project Finance Desk"

    if intent_tag in (
        "Site Visit Request",
        "Construction Update",
        "Broker / Channel Partner",
    ):
        return "Site Operations Desk"

    if intent_tag in (
        "Legal Documentation",
        "Account Access",
    ):
        return "Documentation Desk"

    if intent_tag in (
        "Possession / Handover",
        "Maintenance Request",
    ):
        return "Handover and Maintenance Desk"

    if intent_tag in (
        "Quotation Request",
        "Availability Check",
    ):
        return "Sales Advisory Desk"

    if priority == "High":
        return "Priority Response"

    return f"{issue_type} Queue"


def build_ticket_metadata(
    issue,
    customer_email,
    issue_type,
    priority,
    customer_context=None,
):

    if customer_context is None:
        customer_context = {}

    created_at = get_support_now()
    intent_tag = classify_intent_tag(
        issue,
        issue_type=issue_type,
    )

    return {
        "assignment_method": "Auto-Routed",
        "brand_tag": detect_brand_tag(
            customer_email
        ),
        "business_hours_tag": get_business_hours_tag(
            created_at
        ),
        "created_at": created_at.isoformat(
            timespec="seconds"
        ),
        "intent_tag": intent_tag,
        "queue_name": build_queue_name(
            issue_type,
            priority,
            intent_tag,
            customer_context=customer_context,
        ),
        "updated_at": created_at.isoformat(
            timespec="seconds"
        ),
    }


def enrich_ticket_record(ticket):

    ticket = dict(ticket)

    issue = ticket.get(
        "issue",
        "",
    )

    issue_type = ticket.get(
        "issue_type",
        "General",
    ) or "General"

    priority = ticket.get(
        "priority",
        "Low",
    ) or "Low"

    customer_email = ticket.get(
        "customer_email",
        "",
    )

    metadata = build_ticket_metadata(
        issue=issue,
        customer_email=customer_email,
        issue_type=issue_type,
        priority=priority,
    )

    for key, value in metadata.items():

        if not ticket.get(key):
            ticket[key] = value

    if not ticket.get("assigned_agent"):
        ticket["assigned_agent"] = get_default_agent(
            issue_type,
            ticket.get("intent_tag"),
        )

    return ticket