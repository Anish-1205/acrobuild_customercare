import logging
import os

import requests

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
logger = logging.getLogger(__name__)


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
    normalized_email = str(email or "").strip().lower()
    context = build_default_customer_context()
    if not normalized_email:
        return context
    base_url = os.getenv("NUFOODZ_API_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return context
    timeout = float(timeout_seconds or os.getenv("NUFOODZ_API_TIMEOUT_SECONDS", "3"))
    try:
        response = requests.get(f"{base_url}/api/customer", params={"email": normalized_email}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        customer = payload.get("customer", payload) if isinstance(payload, dict) else {}
        if not isinstance(customer, dict):
            raise ValueError("Customer API returned an invalid object")
        context.update({
            "active_site_visits": first_int_value(customer.get("active_site_visits"), customer.get("activeSiteVisits")),
            "lead_stage": first_non_empty_text(customer.get("lead_stage"), customer.get("leadStage"), "new"),
            "ndis_enabled": first_bool_value(customer.get("ndis_enabled"), customer.get("ndisEnabled"), customer.get("is_ndis")),
            "order_count": first_int_value(customer.get("order_count"), customer.get("orderCount"), customer.get("total_orders")),
            "owns_property": first_bool_value(customer.get("owns_property"), customer.get("ownsProperty")),
            "portfolio_value": first_float_value(customer.get("portfolio_value"), customer.get("portfolioValue")),
            "project_count": first_int_value(customer.get("project_count"), customer.get("projectCount")),
            "total_spent": first_float_value(customer.get("total_spent"), customer.get("totalSpent")),
        })
        context["is_new"] = context["order_count"] == 0 and context["project_count"] == 0
        context["is_vip"] = first_bool_value(customer.get("is_vip"), customer.get("isVip")) or context["order_count"] >= 10 or context["total_spent"] >= 1000
    except (requests.RequestException, ValueError, TypeError):
        logger.exception("Customer context lookup failed for %s", normalized_email)
    return context


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

    from services.intent_service import classify_structured_intent
    from qwen import generate_qwen_chat_response
    decision = classify_structured_intent(issue, customer_context, generate_qwen_chat_response if os.getenv("SUPPORT_LLM_CLASSIFICATION", "false").lower() == "true" else None)
    issue_type = decision.intent if decision.confidence >= 0.7 else classify_issue(issue, customer_context)

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
