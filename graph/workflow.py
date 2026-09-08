
from services.database_service import create_ticket
from services.ticket_metadata_service import (
    build_ticket_metadata,
    classify_intent_tag,
    get_default_agent,
)

DEFAULT_CUSTOMER_CONTEXT = {
    "active_site_visits": 0,
    "is_new": True,
    "is_vip": False,
    "lead_stage": "new",
    "ndis_enabled": False,
    "order_count": 0,
    "owns_property": False,
    "portfolio_value": 0.0,
    "project_count": 0,
    "total_spent": 0.0,
}


# -----------------------------------
# VALUE HELPERS
# -----------------------------------

def build_default_customer_context():

    return dict(
        DEFAULT_CUSTOMER_CONTEXT
    )


def first_non_empty_text(*values):

    for value in values:
        cleaned_value = str(
            value or ""
        ).strip()

        if cleaned_value:
            return cleaned_value

    return ""


def first_int_value(*values):

    for value in values:
        if isinstance(value, bool):
            continue

        if isinstance(value, int):
            return value

        cleaned_value = str(
            value or ""
        ).strip()

        if not cleaned_value:
            continue

        try:
            return int(float(cleaned_value))
        except ValueError:
            continue

    return 0


def first_float_value(*values):

    for value in values:
        if isinstance(value, bool):
            continue

        if isinstance(value, (int, float)):
            return float(value)

        cleaned_value = str(
            value or ""
        ).strip()

        if not cleaned_value:
            continue

        try:
            return float(cleaned_value)
        except ValueError:
            continue

    return 0.0


def first_bool_value(*values):

    for value in values:
        if isinstance(value, bool):
            return value

        cleaned_value = str(
            value or ""
        ).strip().lower()

        if cleaned_value in (
            "1",
            "true",
            "yes",
            "y",
        ):
            return True

        if cleaned_value in (
            "0",
            "false",
            "no",
            "n",
        ):
            return False

    return False


# -----------------------------------
# CUSTOMER CONTEXT
# -----------------------------------

def get_customer_context(email, timeout_seconds=None):
    del email, timeout_seconds
    return build_default_customer_context()


# -----------------------------------
# CLASSIFICATION
# -----------------------------------

def classify_issue(issue, customer_context=None):

    issue_lower = str(
        issue or ""
    ).lower()

    if customer_context is None:
        customer_context = build_default_customer_context()

    if any(
        keyword in issue_lower
        for keyword in (
            "payment",
            "invoice",
            "receipt",
            "refund",
            "booking amount",
            "installment",
            "instalment",
            "emi",
            "outstanding",
            "due amount",
        )
    ):
        return "Payments"

    if any(
        keyword in issue_lower
        for keyword in (
            "password",
            "login",
            "portal",
            "account",
            "sign in",
            "access",
        )
    ):
        return "Account"

    if any(
        keyword in issue_lower
        for keyword in (
            "document",
            "agreement",
            "registration",
            "registry",
            "title deed",
            "approval",
            "noc",
            "loan paper",
            "kyc",
            "legal",
        )
    ):
        return "Documentation"

    if any(
        keyword in issue_lower
        for keyword in (
            "site visit",
            "visit",
            "inspection",
            "tour",
            "sample flat",
            "show apartment",
            "walkthrough",
        )
    ):
        return "Site Visit"

    if any(
        keyword in issue_lower
        for keyword in (
            "handover",
            "possession",
            "snag",
            "fitout",
            "fit-out",
            "key handover",
        )
    ):
        return "Handover"

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
            "defect",
            "repair",
        )
    ):
        return "Maintenance"

    if any(
        keyword in issue_lower
        for keyword in (
            "construction",
            "progress",
            "milestone",
            "timeline",
            "delay",
            "tower update",
            "completion",
        )
    ):
        return "Construction"

    if any(
        keyword in issue_lower
        for keyword in (
            "price",
            "pricing",
            "quote",
            "quotation",
            "availability",
            "inventory",
            "unit",
            "project",
            "apartment",
            "villa",
            "plot",
            "commercial",
            "brochure",
            "floor plan",
            "book",
            "booking",
        )
    ):
        return "Sales"

    if customer_context.get("owns_property"):
        return "Handover"

    return "General"


# -----------------------------------
# PRIORITY
# -----------------------------------

def set_priority(issue_type, customer_context=None, issue=""):

    if customer_context is None:
        customer_context = build_default_customer_context()

    issue_lower = str(
        issue or ""
    ).lower()
    base_priority = {
        "Payments": "High",
        "Documentation": "High",
        "Handover": "High",
        "Maintenance": "High",
        "Account": "Medium",
        "Construction": "Medium",
        "Sales": "Medium",
        "Site Visit": "Medium",
        "General": "Low",
    }.get(issue_type, "Low")

    if any(
        keyword in issue_lower
        for keyword in (
            "urgent",
            "safety",
            "legal notice",
            "fire",
            "electrical fault",
            "water leakage",
            "structural",
        )
    ):
        return "High"

    if base_priority == "Low" and customer_context.get("is_vip"):
        return "Medium"

    if base_priority == "Medium" and customer_context.get("is_vip"):
        return "High"

    return base_priority


# -----------------------------------
# AGENT ASSIGNMENT
# -----------------------------------

def assign_agent(issue_type, customer_context=None):

    intent_tag = classify_intent_tag(
        issue_type,
        issue_type=issue_type,
    )

    return get_default_agent(
        issue_type,
        intent_tag,
        customer_context=customer_context,
    )


# -----------------------------------
# WORKFLOW
# -----------------------------------

def run_workflow(
    issue,
    customer_email="",
    attachments=None,
):

    customer_context = get_customer_context(customer_email)

    issue_type = classify_issue(issue, customer_context)

    priority = set_priority(
        issue_type,
        customer_context,
        issue=issue,
    )

    ticket_metadata = build_ticket_metadata(
        issue=issue,
        customer_email=customer_email,
        issue_type=issue_type,
        priority=priority,
        customer_context=customer_context,
    )

    agent = get_default_agent(
        issue_type,
        ticket_metadata["intent_tag"],
        customer_context=customer_context,
    )

    ticket_id = create_ticket(
        issue=issue,
        customer_email=customer_email,
        issue_type=issue_type,
        priority=priority,
        assigned_agent=agent,
        brand_tag=ticket_metadata["brand_tag"],
        intent_tag=ticket_metadata["intent_tag"],
        business_hours_tag=ticket_metadata["business_hours_tag"],
        queue_name=ticket_metadata["queue_name"],
        assignment_method=ticket_metadata["assignment_method"],
        attachments=attachments,
    )

    return {
        "assigned_agent": agent,
        "assignment_method": ticket_metadata["assignment_method"],
        "brand_tag": ticket_metadata["brand_tag"],
        "business_hours_tag": ticket_metadata["business_hours_tag"],
        "customer_email": customer_email,
        "customer_lead_stage": customer_context["lead_stage"],
        "customer_new": customer_context["is_new"],
        "customer_project_count": customer_context["project_count"],
        "customer_vip": customer_context["is_vip"],
        "intent_tag": ticket_metadata["intent_tag"],
        "issue_type": issue_type,
        "priority": priority,
        "queue_name": ticket_metadata["queue_name"],
        "ticket_id": ticket_id,
    }