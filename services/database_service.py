import json
import mimetypes
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from services.admin_settings_service import (
    apply_workflow_rules_to_ticket,
    initialize_admin_settings,
    remove_ticket_tag_links,
    refresh_ticket_business_hours_labels,
    sync_workflow_rule_tags,
)
from services.ticket_metadata_service import (
    enrich_ticket_record,
    get_default_agent,
    get_ticket_timestamp,
)

DB_PATH = str(
    Path(__file__).resolve().parent.parent
    / "support_system.db"
)
PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)
MESSAGE_UPLOAD_DIR = (
    PROJECT_ROOT
    / "data"
    / "message_uploads"
)
SQLITE_BUSY_TIMEOUT_MS = 30000
REQUIRED_BOOTSTRAP_TABLES = {
    "business_hour_ranges",
    "business_hours_profiles",
    "business_hours_rule_windows",
    "knowledge_documents",
    "macro_tags",
    "macros",
    "messages",
    "support_articles",
    "support_users",
    "tags",
    "ticket_counters",
    "ticket_notes",
    "ticket_tag_links",
    "tickets",
    "workflow_rules",
}


def open_database_connection():

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )
    conn.execute(
        f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}"
    )
    conn.execute(
        "PRAGMA journal_mode = WAL"
    )

    return conn


def database_bootstrap_is_complete(cursor):

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    )

    existing_tables = {
        row[0]
        for row in cursor.fetchall()
    }

    return REQUIRED_BOOTSTRAP_TABLES.issubset(
        existing_tables
    )


# -----------------------------------
# SCHEMA HELPERS
# -----------------------------------

def ensure_column(
    cursor,
    table_name,
    column_name,
    column_definition
):

    cursor.execute(
        f"PRAGMA table_info({table_name})"
    )

    columns = {
        row[1]
        for row in cursor.fetchall()
    }

    if column_name not in columns:

        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {column_definition}
            """
        )


def normalize_attachment_name(value):

    return re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        str(value or "").strip(),
    ).strip("-") or "attachment"


def ensure_message_upload_dir():

    MESSAGE_UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def read_uploaded_attachment(uploaded_attachment):

    if uploaded_attachment is None:
        return b"", "", ""

    if isinstance(
        uploaded_attachment,
        dict,
    ):
        file_name = Path(
            str(
                uploaded_attachment.get(
                    "name",
                    "attachment",
                )
            )
        ).name
        mime_type = str(
            uploaded_attachment.get(
                "mime_type"
            )
            or uploaded_attachment.get(
                "type"
            )
            or ""
        ).strip()
        file_bytes = (
            uploaded_attachment.get(
                "bytes"
            )
            or uploaded_attachment.get(
                "content"
            )
            or b""
        )

        if isinstance(
            file_bytes,
            str,
        ):
            file_bytes = file_bytes.encode(
                "utf-8"
            )

        return (
            bytes(file_bytes),
            file_name,
            mime_type,
        )

    file_name = Path(
        str(
            getattr(
                uploaded_attachment,
                "name",
                "attachment",
            )
        )
    ).name
    mime_type = str(
        getattr(
            uploaded_attachment,
            "type",
            "",
        )
        or ""
    ).strip()

    if hasattr(
        uploaded_attachment,
        "getvalue",
    ):
        file_bytes = uploaded_attachment.getvalue()
    elif hasattr(
        uploaded_attachment,
        "read",
    ):
        file_bytes = uploaded_attachment.read()
    else:
        file_bytes = b""

    try:
        if hasattr(
            uploaded_attachment,
            "seek",
        ):
            uploaded_attachment.seek(0)
    except Exception:
        pass

    return (
        bytes(file_bytes or b""),
        file_name,
        mime_type,
    )


def persist_message_attachments(
    ticket_id,
    attachments=None,
):

    if not attachments:
        return []

    ensure_message_upload_dir()

    attachment_records = []
    timestamp_fragment = (
        get_ticket_timestamp()
        .replace(":", "")
        .replace("-", "")
        .replace("+", "")
        .replace("T", "_")
    )

    for index, attachment in enumerate(
        attachments,
        start=1,
    ):
        (
            file_bytes,
            file_name,
            mime_type,
        ) = read_uploaded_attachment(
            attachment
        )

        if not file_bytes:
            continue

        suffix = Path(file_name).suffix.lower()

        if not suffix:
            suffix = (
                mimetypes.guess_extension(
                    mime_type or ""
                )
                or ".png"
            )

        inferred_mime_type = (
            mime_type
            or mimetypes.guess_type(
                file_name
            )[0]
            or "application/octet-stream"
        )

        if not inferred_mime_type.startswith(
            "image/"
        ):
            continue

        stored_name = (
            f"{str(ticket_id).lower()}_"
            f"{timestamp_fragment}_"
            f"{index}_"
            f"{uuid4().hex[:8]}_"
            f"{normalize_attachment_name(Path(file_name).stem)}"
            f"{suffix}"
        )
        file_path = (
            MESSAGE_UPLOAD_DIR
            / stored_name
        )
        file_path.write_bytes(
            file_bytes
        )

        attachment_records.append(
            {
                "name": file_name
                or f"image-{index}{suffix}",
                "path": str(
                    file_path.relative_to(
                        PROJECT_ROOT
                    )
                ).replace(
                    "\\",
                    "/",
                ),
                "mime_type": inferred_mime_type,
                "size_bytes": len(
                    file_bytes
                ),
            }
        )

    return attachment_records


def parse_message_attachments(raw_value):

    text = str(
        raw_value or ""
    ).strip()

    if not text:
        return []

    try:
        records = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(
        records,
        list,
    ):
        return []

    attachments = []

    for record in records:
        if not isinstance(
            record,
            dict,
        ):
            continue

        relative_path = str(
            record.get("path", "")
        ).strip()

        if not relative_path:
            continue

        absolute_path = (
            PROJECT_ROOT
            / relative_path
        )

        attachments.append(
            {
                "name": str(
                    record.get(
                        "name",
                        "image",
                    )
                ),
                "path": relative_path,
                "absolute_path": str(
                    absolute_path
                ),
                "mime_type": str(
                    record.get(
                        "mime_type",
                        "",
                    )
                ),
                "size_bytes": int(
                    record.get(
                        "size_bytes",
                        0,
                    )
                    or 0
                ),
                "exists": absolute_path.exists(),
            }
        )

    return attachments


def ensure_ticket_counter(cursor):

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_counters (
            name TEXT PRIMARY KEY,
            next_value INTEGER NOT NULL
        )
        """
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO ticket_counters (
            name,
            next_value
        )
        VALUES ('ticket_id', 1)
        """
    )


def is_modern_ticket_id(ticket_id):

    if not isinstance(ticket_id, str):
        return False

    normalized_ticket_id = ticket_id.strip().upper()

    return (
        normalized_ticket_id.startswith("TK")
        and len(normalized_ticket_id) == 8
        and normalized_ticket_id[2:].isdigit()
    )


def get_highest_ticket_sequence(cursor):

    cursor.execute(
        """
        SELECT ticket_id
        FROM tickets
        """
    )

    highest_sequence = 0

    for (ticket_id,) in cursor.fetchall():

        if is_modern_ticket_id(ticket_id):
            highest_sequence = max(
                highest_sequence,
                int(ticket_id[2:]),
            )

    return highest_sequence


def sync_ticket_counter(cursor):

    ensure_ticket_counter(cursor)

    cursor.execute(
        """
        SELECT next_value
        FROM ticket_counters
        WHERE name = 'ticket_id'
        """
    )

    row = cursor.fetchone()
    current_next_value = int(row[0] if row else 1)
    required_next_value = (
        get_highest_ticket_sequence(cursor)
        + 1
    )
    synced_next_value = max(
        current_next_value,
        required_next_value,
    )

    cursor.execute(
        """
        UPDATE ticket_counters
        SET next_value = ?
        WHERE name = 'ticket_id'
        """,
        (synced_next_value,)
    )

    return synced_next_value


def migrate_legacy_ticket_ids(cursor):

    ensure_ticket_counter(cursor)

    cursor.execute(
        """
        SELECT rowid, ticket_id
        FROM tickets
        ORDER BY rowid ASC
        """
    )

    legacy_tickets = [
        (row_id, ticket_id)
        for row_id, ticket_id in cursor.fetchall()
        if not is_modern_ticket_id(ticket_id)
    ]

    if not legacy_tickets:
        sync_ticket_counter(cursor)
        return

    next_sequence = (
        get_highest_ticket_sequence(cursor)
        + 1
    )

    for row_id, legacy_ticket_id in legacy_tickets:

        new_ticket_id = (
            f"TK{next_sequence:06d}"
        )

        cursor.execute(
            """
            UPDATE messages
            SET ticket_id = ?
            WHERE ticket_id = ?
            """,
            (
                new_ticket_id,
                legacy_ticket_id,
            )
        )

        cursor.execute(
            """
            UPDATE tickets
            SET ticket_id = ?
            WHERE rowid = ?
            """,
            (
                new_ticket_id,
                row_id,
            )
        )

        next_sequence += 1

    cursor.execute(
        """
        UPDATE ticket_counters
        SET next_value = ?
        WHERE name = 'ticket_id'
        """,
        (next_sequence,)
    )


def generate_next_ticket_id(cursor):

    sync_ticket_counter(cursor)

    cursor.execute(
        """
        SELECT next_value
        FROM ticket_counters
        WHERE name = 'ticket_id'
        """
    )

    row = cursor.fetchone()
    next_value = int(row[0] if row else 1)

    cursor.execute(
        """
        UPDATE ticket_counters
        SET next_value = ?
        WHERE name = 'ticket_id'
        """,
        (next_value + 1,)
    )

    return f"TK{next_value:06d}"


DEFAULT_SUPPORT_ARTICLES = [
    {
        "body": (
            "To book a site visit, please share the project or property, your preferred date, a convenient time window, "
            "your name, and the best callback number. Our site coordinator will check availability and confirm the appointment. "
            "The requested slot is not final until you receive confirmation. You can send those details here now."
        ),
        "category": "Site Visit",
        "keywords": [
            "site visit",
            "inspection",
            "sample flat",
            "tour",
            "project visit",
        ],
        "status": "Published",
        "summary": (
            "The details needed to request a site visit and how appointment confirmation works."
        ),
        "title": "Site visit booking checklist",
        "url": "",
    },
    {
        "body": (
            "Use this article to explain how pricing checks, unit availability, and quotation follow-up should be handled "
            "for apartments, villas, plots, and commercial inventory."
        ),
        "category": "Sales",
        "keywords": [
            "quotation",
            "pricing",
            "availability",
            "inventory",
            "brochure",
        ],
        "status": "Published",
        "summary": (
            "Guidance for project quotations, inventory checks, and brochure-style sales follow-up."
        ),
        "title": "Quotation and inventory follow-up playbook",
        "url": "",
    },
    {
        "body": (
            "For help with a payment, please share your project or unit reference, transaction reference, amount paid, "
            "payment date, payment method, and whether you need a receipt, invoice, or ledger correction. The finance team "
            "will verify the transaction before confirming any update. Never share your card PIN or OTP in chat."
        ),
        "category": "Payments",
        "keywords": [
            "payment",
            "receipt",
            "invoice",
            "ledger",
            "emi",
        ],
        "status": "Published",
        "summary": (
            "The details customers should provide for receipts, invoices, ledger corrections, and payment questions."
        ),
        "title": "Payment receipts and ledger clarification",
        "url": "",
    },
    {
        "body": (
            "Construction progress replies should stay aligned with confirmed project milestones. "
            "Do not promise exact completion or possession dates unless the approved update already confirms them."
        ),
        "category": "Construction",
        "keywords": [
            "construction",
            "progress",
            "milestone",
            "timeline",
            "delay",
        ],
        "status": "Published",
        "summary": (
            "Response guidance for construction updates, milestone questions, and delay follow-up."
        ),
        "title": "Construction progress update playbook",
        "url": "",
    },
    {
        "body": (
            "When buyers ask for agreements, approvals, registration, NOC, or KYC-linked documents, "
            "confirm the project, booking reference, and document name before routing the request to documentation support."
        ),
        "category": "Documentation",
        "keywords": [
            "agreement",
            "registration",
            "approval",
            "noc",
            "kyc",
        ],
        "status": "Published",
        "summary": (
            "Checklist guidance for legal, registration, and documentation requests."
        ),
        "title": "Legal documents and registration checklist",
        "url": "",
    },
    {
        "body": (
            "Handover and maintenance cases should capture the project name, tower or unit reference, and photo or video evidence. "
            "Safety-sensitive defects must be escalated immediately."
        ),
        "category": "Handover",
        "keywords": [
            "handover",
            "possession",
            "maintenance",
            "defect",
            "snag",
        ],
        "status": "Published",
        "summary": (
            "How to triage possession, snag, and maintenance issues with the Acrobuild care team."
        ),
        "title": "Handover and maintenance triage guide",
        "url": "",
    },
    {
        "body": (
            "For after-hours tickets, let customers know their request is queued for the next service window "
            "and clarify which urgent construction, payment, or maintenance issues are escalated immediately."
        ),
        "category": "Operations",
        "keywords": [
            "business hours",
            "after hours",
            "response time",
            "sla",
        ],
        "status": "Published",
        "summary": (
            "Sets reply-time expectations for requests raised outside business hours."
        ),
        "title": "Business-hours and after-hours expectations",
        "url": "",
    },
]

DEFAULT_SUPPORT_ARTICLES.extend([
    {
        "title": "Site appointment confirmation and rescheduling",
        "category": "Site Visit", "status": "Published", "url": "",
        "keywords": ["appointment", "book appointment", "uncertain appointment", "reschedule", "site coordinator", "visit slot"],
        "summary": "Scheduling, rescheduling, and confirming site appointments when availability is uncertain.",
        "body": "Collect the project, visitor names, preferred date window, visit purpose, and callback number. A requested slot is not confirmed until the site coordinator approves safe access. If unavailable, offer the next two windows. Never promise immediate entry because inspections, active work, and safety restrictions can change access."
    },
    {
        "title": "Daily construction site progress update",
        "category": "Construction", "status": "Published", "url": "",
        "keywords": ["daily update", "site report", "today progress", "work completed", "site engineer", "progress photo"],
        "summary": "A practical format for verified daily progress updates from an active site.",
        "body": "Identify the project zone, work completed today, work planned next, labour or equipment constraints, safety observations, and decisions needed. Share only progress verified by the site engineer or approved report. Progress photos should include date, location, and a clear caption."
    },
    {
        "title": "Weather delay and recovery plan guidance",
        "category": "Construction", "status": "Published", "url": "",
        "keywords": ["rain delay", "weather", "waterlogging", "high wind", "heat", "lost shift", "recovery plan"],
        "summary": "Communicating weather stoppages, recovery planning, and timeline impact responsibly.",
        "body": "Explain which activity is paused and which protected work can continue during rain, wind, heat, or waterlogging. Do not calculate a new completion date from one event. Record the lost shift, safety reason, recovery action, responsible owner, and next milestone review date."
    },
    {
        "title": "Concrete pour and structural milestone checks",
        "category": "Construction", "status": "Published", "url": "",
        "keywords": ["concrete pour", "slab", "column", "formwork", "reinforcement", "cube test", "structural milestone"],
        "summary": "Pre-pour checks for slabs, columns, and concrete milestones.",
        "body": "Confirm approved drawings, reinforcement and formwork inspection, concrete grade, pour area, cube-test plan, pump access, and weather. If any pre-pour approval is pending, describe the milestone as planned instead of confirmed and provide the next inspection checkpoint."
    },
    {
        "title": "Construction material delivery and shortage handling",
        "category": "Site Operations", "status": "Published", "url": "",
        "keywords": ["material delivery", "supplier", "cement", "steel", "tiles", "short delivery", "damaged material"],
        "summary": "Tracking deliveries, shortages, damage, unloading, and acceptance at the site gate.",
        "body": "Capture material, supplier, delivery reference, expected quantity, arrival time, unloading zone, and inspection status. Damaged, short, or non-compliant material must be quarantined and reviewed. Do not report delivery as accepted until quality checks are complete."
    },
    {
        "title": "Active construction site safety and visitor access",
        "category": "Safety", "status": "Published", "url": "",
        "keywords": ["safety", "ppe", "helmet", "visitor access", "site induction", "restricted zone", "safety shoes"],
        "summary": "Visitor access, PPE, induction, escort, and restricted-zone rules.",
        "body": "Confirm identity, approved appointment, induction, escort, restricted zones, and PPE including helmet, vest, and safety shoes. Children and unescorted visitors must not enter work zones. Unsafe conditions go immediately to the safety officer; emergencies go to site emergency response."
    },
    {
        "title": "Quality inspection and defect escalation",
        "category": "Quality", "status": "Published", "url": "",
        "keywords": ["quality inspection", "defect", "non conformance", "ncr", "reinspection", "waterproofing", "crack"],
        "summary": "Capturing defects, corrective work, evidence, and reinspection status.",
        "body": "Record exact location, drawing or specification, observed defect, photos, inspection date, and responsible trade. Track open, under correction, ready for reinspection, or closed status. Structural cracks, waterproofing failures, and safety defects require priority engineering review."
    },
    {
        "title": "Design change and variation approval workflow",
        "category": "Design Changes", "status": "Published", "url": "",
        "keywords": ["change order", "variation", "design change", "drawing revision", "additional cost", "scope change"],
        "summary": "Controlling variations, drawing revisions, approval, cost, and schedule impact.",
        "body": "A variation is not approved until scope, drawing revision, cost, schedule impact, and authorized sign-off are recorded. Confirm whether work started and whether a hold is required. Never instruct a contractor from an informal chat message or unapproved buyer request."
    },
    {
        "title": "Contractor coordination and blocked work resolution",
        "category": "Site Operations", "status": "Published", "url": "",
        "keywords": ["contractor", "subcontractor", "labour", "crew", "coordination", "blocked work", "equipment"],
        "summary": "Resolving dependencies, missing crews, blocked work fronts, and contractor commitments.",
        "body": "Record area, contractor, prerequisite activity, planned crew, equipment, start window, and blocker. Escalate when one trade prevents another from working or a committed crew does not arrive. State the action owner and next coordination time."
    },
    {
        "title": "Site utility interruption and emergency escalation",
        "category": "Site Operations", "status": "Published", "url": "",
        "keywords": ["power cut", "water supply", "lift", "drainage", "utility shutdown", "exposed wire", "flooding"],
        "summary": "Triage for temporary utilities, shutdowns, and urgent service hazards.",
        "body": "Confirm affected area, start time, safety risk, responsible team, and review time for electricity, water, lift, or drainage interruptions. Notify impacted occupants and trades. Fire, flooding, exposed wiring, gas smell, and trapped-person reports require immediate emergency escalation."
    },
    {
        "title": "Neighbour complaint and site nuisance response",
        "category": "Community", "status": "Published", "url": "",
        "keywords": ["noise", "dust", "neighbour complaint", "debris", "traffic", "working hours", "pollution"],
        "summary": "Responding to construction noise, dust, traffic, debris, and neighbour concerns.",
        "body": "Record time, location, activity, affected party, and evidence. Confirm permitted working hours and controls such as water suppression, barricading, covered transport, and traffic marshals. Repeated complaints go to project and safety leads with a callback commitment."
    },
    {
        "title": "Pre-handover readiness and possession scheduling",
        "category": "Handover", "status": "Published", "url": "",
        "keywords": ["pre handover", "possession date", "snag inspection", "keys", "readiness", "handover appointment"],
        "summary": "Readiness checks for possession, snagging, keys, and handover appointments.",
        "body": "Confirm completion, statutory dependencies, utilities, common-area access, snag inspection, documents, and outstanding payments. A requested handover date is not confirmed until readiness is validated. Provide the next review date and a named follow-up owner."
    },
])
LEGACY_SUPPORT_ARTICLE_TITLES = {
    "Damaged order replacement policy",
    "Delivery delay follow-up playbook",
    "Refund and store credit rules",
    "Subscription update and skip guide",
}


def parse_json_string_list(raw_value):

    text = str(
        raw_value or ""
    ).strip()

    if not text:
        return []

    try:
        records = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(
        records,
        list,
    ):
        return []

    return [
        str(record).strip()
        for record in records
        if str(record).strip()
    ]


def seed_default_support_users(cursor):

    timestamp = get_ticket_timestamp()
    legacy_email_updates = [
        (
            "owner@acrobuild.com",
            "Michael Ross",
            "Leadership",
            "michael@acrobuild.com",
        ),
        (
            "admin@acrobuild.com",
            "Sarah Khan",
            "Operations",
            "sarah@acrobuild.com",
        ),
        (
            "agent@acrobuild.com",
            "John Lewis",
            "Site Operations",
            "agent@nufooz.com",
        ),
        (
            "anika@acrobuild.com",
            "Anika Patel",
            "Project Support",
            "anika@acrobuild.com",
        ),
    ]

    for (
        next_email,
        next_name,
        next_team,
        legacy_email,
    ) in legacy_email_updates:
        cursor.execute(
            """
            SELECT id
            FROM support_users
            WHERE email = ?
            """,
            (legacy_email,)
        )

        legacy_row = cursor.fetchone()

        if not legacy_row:
            continue

        cursor.execute(
            """
            SELECT id
            FROM support_users
            WHERE email = ?
            """,
            (next_email,)
        )

        if cursor.fetchone():
            continue

        cursor.execute(
            """
            UPDATE support_users
            SET email = ?,
                name = ?,
                team = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                next_email,
                next_name,
                next_team,
                timestamp,
                int(legacy_row[0]),
            )
        )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM support_users
        """
    )

    row = cursor.fetchone()
    existing_count = int(row[0] if row else 0)

    if existing_count > 0:
        return

    default_users = [
        (
            "Michael Ross",
            "owner@acrobuild.com",
            "owner",
            "Leadership",
            "Active",
            "demo@123",
            timestamp,
            timestamp,
        ),
        (
            "Sarah Khan",
            "admin@acrobuild.com",
            "admin",
            "Operations",
            "Active",
            "demo@123",
            timestamp,
            timestamp,
        ),
        (
            "John Lewis",
            "agent@acrobuild.com",
            "agent",
            "Site Operations",
            "Active",
            "demo@123",
            timestamp,
            timestamp,
        ),
        (
            "Anika Patel",
            "anika@acrobuild.com",
            "agent",
            "Project Support",
            "Invited",
            "demo@123",
            timestamp,
            timestamp,
        ),
    ]

    cursor.executemany(
        """
        INSERT INTO support_users (
            name,
            email,
            role,
            team,
            status,
            password,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        default_users,
    )


def seed_default_support_articles(cursor):

    timestamp = get_ticket_timestamp()
    cursor.execute(
        """
        UPDATE support_articles
        SET status = 'Draft',
            updated_at = ?
        WHERE title IN (?, ?, ?, ?)
        """,
        (
            timestamp,
            "Damaged order replacement policy",
            "Delivery delay follow-up playbook",
            "Refund and store credit rules",
            "Subscription update and skip guide",
        ),
    )

    for article in DEFAULT_SUPPORT_ARTICLES:
        cursor.execute(
            """
            SELECT id
            FROM support_articles
            WHERE title = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (article["title"],)
        )
        existing_row = cursor.fetchone()

        if existing_row:
            cursor.execute(
                """
                UPDATE support_articles
                SET category = ?,
                    status = ?,
                    summary = ?,
                    body = ?,
                    keywords_json = ?,
                    url = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    article["category"],
                    article["status"],
                    article["summary"],
                    article["body"],
                    json.dumps(article["keywords"]),
                    article["url"],
                    timestamp,
                    int(existing_row[0]),
                )
            )
            continue

        cursor.execute(
            """
            INSERT INTO support_articles (
                title,
                category,
                status,
                summary,
                body,
                keywords_json,
                url,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article["title"],
                article["category"],
                article["status"],
                article["summary"],
                article["body"],
                json.dumps(article["keywords"]),
                article["url"],
                timestamp,
                timestamp,
            )
        )

# -----------------------------------
# INITIALIZE DATABASE
# -----------------------------------

def initialize_database():

    conn = open_database_connection()

    cursor = conn.cursor()

    if database_bootstrap_is_complete(
        cursor
    ):
        seed_default_support_articles(cursor)
        conn.commit()
        conn.close()
        return

    # -----------------------------------
    # TICKETS TABLE
    # -----------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (

            ticket_id TEXT PRIMARY KEY,

            issue TEXT,

            customer_email TEXT,

            issue_type TEXT,

            priority TEXT,

            status TEXT,

            assigned_agent TEXT,

            unread_count INTEGER DEFAULT 0
        )
        """
    )

    ensure_column(
        cursor,
        "tickets",
        "customer_email",
        "TEXT"
    )

    ensure_column(
        cursor,
        "tickets",
        "brand_tag",
        "TEXT"
    )

    ensure_column(
        cursor,
        "tickets",
        "intent_tag",
        "TEXT"
    )

    ensure_column(
        cursor,
        "tickets",
        "business_hours_tag",
        "TEXT"
    )

    ensure_column(
        cursor,
        "tickets",
        "queue_name",
        "TEXT"
    )

    ensure_column(
        cursor,
        "tickets",
        "assignment_method",
        "TEXT"
    )

    ensure_column(
        cursor,
        "tickets",
        "created_at",
        "TEXT"
    )

    ensure_column(
        cursor,
        "tickets",
        "updated_at",
        "TEXT"
    )

    # -----------------------------------
    # MESSAGES TABLE
    # -----------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            ticket_id TEXT,

            sender TEXT,

            message TEXT,

            created_at TEXT,

            attachments_json TEXT DEFAULT '[]'
        )
        """
    )

    ensure_column(
        cursor,
        "messages",
        "created_at",
        "TEXT",
    )

    ensure_column(
        cursor,
        "messages",
        "attachments_json",
        "TEXT DEFAULT '[]'",
    )

    # -----------------------------------
    # USERS TABLE
    # -----------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS support_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL,
            team TEXT DEFAULT 'Support',
            status TEXT DEFAULT 'Active',
            password TEXT DEFAULT 'demo@123',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    ensure_column(
        cursor,
        "support_users",
        "team",
        "TEXT DEFAULT 'Support'"
    )

    ensure_column(
        cursor,
        "support_users",
        "status",
        "TEXT DEFAULT 'Active'"
    )

    ensure_column(
        cursor,
        "support_users",
        "password",
        "TEXT DEFAULT 'demo@123'"
    )

    ensure_column(
        cursor,
        "support_users",
        "created_at",
        "TEXT"
    )

    ensure_column(
        cursor,
        "support_users",
        "updated_at",
        "TEXT"
    )

    seed_default_support_users(cursor)

    # -----------------------------------
    # SUPPORT ARTICLES TABLE
    # -----------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS support_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'Support',
            status TEXT DEFAULT 'Draft',
            summary TEXT DEFAULT '',
            body TEXT DEFAULT '',
            keywords_json TEXT DEFAULT '[]',
            url TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    ensure_column(
        cursor,
        "support_articles",
        "category",
        "TEXT DEFAULT 'Support'"
    )

    ensure_column(
        cursor,
        "support_articles",
        "status",
        "TEXT DEFAULT 'Draft'"
    )

    ensure_column(
        cursor,
        "support_articles",
        "summary",
        "TEXT DEFAULT ''"
    )

    ensure_column(
        cursor,
        "support_articles",
        "body",
        "TEXT DEFAULT ''"
    )

    ensure_column(
        cursor,
        "support_articles",
        "keywords_json",
        "TEXT DEFAULT '[]'"
    )

    ensure_column(
        cursor,
        "support_articles",
        "url",
        "TEXT DEFAULT ''"
    )

    ensure_column(
        cursor,
        "support_articles",
        "created_at",
        "TEXT"
    )

    ensure_column(
        cursor,
        "support_articles",
        "updated_at",
        "TEXT"
    )

    seed_default_support_articles(cursor)

    # -----------------------------------
    # KNOWLEDGE DOCUMENTS TABLE
    # -----------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'Knowledge',
            status TEXT DEFAULT 'Draft',
            summary TEXT DEFAULT '',
            body TEXT DEFAULT '',
            tags_json TEXT DEFAULT '[]',
            source_name TEXT DEFAULT '',
            source_type TEXT DEFAULT 'manual',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "category",
        "TEXT DEFAULT 'Knowledge'"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "status",
        "TEXT DEFAULT 'Draft'"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "summary",
        "TEXT DEFAULT ''"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "body",
        "TEXT DEFAULT ''"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "tags_json",
        "TEXT DEFAULT '[]'"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "source_name",
        "TEXT DEFAULT ''"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "source_type",
        "TEXT DEFAULT 'manual'"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "created_at",
        "TEXT"
    )

    ensure_column(
        cursor,
        "knowledge_documents",
        "updated_at",
        "TEXT"
    )

    ensure_ticket_counter(cursor)
    migrate_legacy_ticket_ids(cursor)
    sync_ticket_counter(cursor)

    # -----------------------------------
    # INTERNAL NOTES TABLE
    # -----------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_notes (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            ticket_id TEXT,

            author TEXT,

            note TEXT,

            created_at TEXT
        )
        """
    )

    cursor.execute(
        """
        SELECT *
        FROM tickets
        """
    )

    existing_ticket_rows = cursor.fetchall()
    ticket_columns = [
        column[1]
        for column in cursor.execute(
            "PRAGMA table_info(tickets)"
        ).fetchall()
    ]

    for row in existing_ticket_rows:

        ticket = dict(
            zip(ticket_columns, row)
        )

        normalized_ticket = enrich_ticket_record(
            ticket
        )

        assigned_agent = (
            normalized_ticket.get(
                "assigned_agent"
            )
            or get_default_agent(
                normalized_ticket.get(
                    "issue_type",
                    "General",
                ),
                normalized_ticket.get(
                    "intent_tag",
                    "General Inquiry",
                ),
            )
        )

        cursor.execute(
            """
            UPDATE tickets
            SET brand_tag = ?,
                intent_tag = ?,
                business_hours_tag = ?,
                queue_name = ?,
                assignment_method = ?,
                created_at = ?,
                updated_at = ?,
                assigned_agent = ?,
                status = COALESCE(status, 'Open'),
                priority = COALESCE(priority, 'Low'),
                issue_type = COALESCE(issue_type, 'General')
            WHERE ticket_id = ?
            """,
            (
                normalized_ticket.get("brand_tag"),
                normalized_ticket.get("intent_tag"),
                normalized_ticket.get("business_hours_tag"),
                normalized_ticket.get("queue_name"),
                normalized_ticket.get("assignment_method"),
                normalized_ticket.get("created_at"),
                normalized_ticket.get("updated_at"),
                assigned_agent,
                normalized_ticket.get("ticket_id"),
            )
        )

    conn.commit()

    conn.close()

    initialize_admin_settings()
    refresh_ticket_business_hours_labels()
    sync_workflow_rule_tags()

# -----------------------------------
# CREATE TICKET
# -----------------------------------

def create_ticket(
    issue,
    customer_email,
    issue_type,
    priority,
    assigned_agent,
    brand_tag="",
    intent_tag="",
    business_hours_tag="",
    queue_name="",
    assignment_method="Auto-Routed",
    attachments=None,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    ticket_id = generate_next_ticket_id(
        cursor
    )
    timestamp = get_ticket_timestamp()

    cursor.execute(
        """
        INSERT INTO tickets (

            ticket_id,
            issue,
            customer_email,
            issue_type,
            priority,
            status,
            assigned_agent,
            brand_tag,
            intent_tag,
            business_hours_tag,
            queue_name,
            assignment_method,
            created_at,
            updated_at

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            issue,
            customer_email,
            issue_type,
            priority,
            "Open",
            assigned_agent,
            brand_tag,
            intent_tag,
            business_hours_tag,
            queue_name,
            assignment_method,
            timestamp,
            timestamp,
        )
    )

    # FIRST MESSAGE

    cursor.execute(
        """
        INSERT INTO messages (

            ticket_id,
            sender,
            message,
            created_at,
            attachments_json

        )

        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            "customer",
            issue,
            timestamp,
            json.dumps(
                persist_message_attachments(
                    ticket_id,
                    attachments=attachments,
                )
            ),
        )
    )

    conn.commit()

    conn.close()

    apply_workflow_rules_to_ticket(
        ticket_id
    )

    return ticket_id

# -----------------------------------
# GET ALL TICKETS
# -----------------------------------

def get_all_tickets():

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM tickets
        """
    )

    rows = cursor.fetchall()

    conn.close()

    return [
        enrich_ticket_record(dict(row))
        for row in rows
    ]

# -----------------------------------
# GET SINGLE TICKET
# -----------------------------------

def get_ticket(ticket_id):

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM tickets
        WHERE ticket_id = ?
        """,
        (ticket_id,)
    )

    row = cursor.fetchone()

    conn.close()

    if row:
        return enrich_ticket_record(
            dict(row)
        )

    return None

# -----------------------------------
# GET TICKET MESSAGES
# -----------------------------------

def get_ticket_messages(ticket_id):

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM messages
        WHERE ticket_id = ?
        ORDER BY id ASC
        """,
        (ticket_id,)
    )

    rows = cursor.fetchall()

    conn.close()

    messages = []

    for row in rows:
        message_entry = dict(row)
        message_entry["attachments"] = (
            parse_message_attachments(
                message_entry.get(
                    "attachments_json"
                )
            )
        )
        messages.append(
            message_entry
        )

    return messages

# -----------------------------------
# INTERNAL NOTES
# -----------------------------------

def get_ticket_notes(ticket_id):

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM ticket_notes
        WHERE ticket_id = ?
        ORDER BY id DESC
        """,
        (ticket_id,)
    )

    rows = cursor.fetchall()

    conn.close()

    messages = []

    for row in rows:
        message_entry = dict(row)
        message_entry["attachments"] = (
            parse_message_attachments(
                message_entry.get(
                    "attachments_json"
                )
            )
        )
        messages.append(
            message_entry
        )

    return messages


def save_ticket_note(
    ticket_id,
    note,
    author="Admin",
):

    cleaned_note = str(note).strip()

    if not cleaned_note:
        return

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    timestamp = get_ticket_timestamp()

    cursor.execute(
        """
        INSERT INTO ticket_notes (

            ticket_id,
            author,
            note,
            created_at

        )

        VALUES (?, ?, ?, ?)
        """,
        (
            ticket_id,
            author,
            cleaned_note,
            timestamp,
        )
    )

    cursor.execute(
        """
        UPDATE tickets
        SET updated_at = ?
        WHERE ticket_id = ?
        """,
        (
            timestamp,
            ticket_id,
        )
    )

    conn.commit()

    conn.close()

# -----------------------------------
# SAVE MESSAGE
# -----------------------------------

def save_message(
    ticket_id,
    sender,
    message,
    attachments=None,
):

    cleaned_message = str(
        message or ""
    ).strip()
    attachment_records = (
        persist_message_attachments(
            ticket_id,
            attachments=attachments,
        )
    )

    if (
        not cleaned_message
        and not attachment_records
    ):
        return None

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()
    timestamp = get_ticket_timestamp()

    cursor.execute(
        """
        INSERT INTO messages (

            ticket_id,
            sender,
            message,
            created_at,
            attachments_json

        )

        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            sender,
            cleaned_message,
            timestamp,
            json.dumps(
                attachment_records
            ),
        )
    )

    # UPDATE UNREAD COUNT

    if sender == "customer":

        cursor.execute(
            """
            UPDATE tickets
            SET unread_count = unread_count + 1
            WHERE ticket_id = ?
            """,
            (ticket_id,)
        )

    cursor.execute(
        """
        UPDATE tickets
        SET updated_at = ?
        WHERE ticket_id = ?
        """,
        (
            timestamp,
            ticket_id,
        )
    )

    message_id = int(
        cursor.lastrowid
    )
    conn.commit()

    conn.close()

    return {
        "id": message_id,
        "ticket_id": ticket_id,
        "sender": sender,
        "message": cleaned_message,
        "created_at": timestamp,
        "attachments": [
            {
                **attachment,
                "absolute_path": str(
                    PROJECT_ROOT
                    / attachment["path"]
                ),
                "exists": (
                    PROJECT_ROOT
                    / attachment["path"]
                ).exists(),
            }
            for attachment in attachment_records
        ],
    }


# -----------------------------------
# ATTACH TO LATEST MESSAGE
# -----------------------------------

def attach_attachments_to_latest_message(
    ticket_id,
    sender,
    attachments=None,
):

    attachment_records = (
        persist_message_attachments(
            ticket_id,
            attachments=attachments,
        )
    )

    if not attachment_records:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    timestamp = get_ticket_timestamp()

    cursor.execute(
        """
        SELECT id, attachments_json
        FROM messages
        WHERE ticket_id = ? AND sender = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            ticket_id,
            sender,
        ),
    )

    row = cursor.fetchone()

    if row is None:
        merged_records = attachment_records

        cursor.execute(
            """
            INSERT INTO messages (

                ticket_id,
                sender,
                message,
                created_at,
                attachments_json

            )

            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                sender,
                "",
                timestamp,
                json.dumps(
                    merged_records
                ),
            ),
        )

        if sender == "customer":

            cursor.execute(
                """
                UPDATE tickets
                SET unread_count = unread_count + 1
                WHERE ticket_id = ?
                """,
                (ticket_id,),
            )

    else:
        existing_raw_value = str(
            row["attachments_json"] or "[]"
        ).strip()

        try:
            existing_records = json.loads(
                existing_raw_value
            )
        except json.JSONDecodeError:
            existing_records = []

        if not isinstance(
            existing_records,
            list,
        ):
            existing_records = []

        merged_records = (
            existing_records
            + attachment_records
        )

        cursor.execute(
            """
            UPDATE messages
            SET attachments_json = ?
            WHERE id = ?
            """,
            (
                json.dumps(
                    merged_records
                ),
                row["id"],
            ),
        )

    cursor.execute(
        """
        UPDATE tickets
        SET updated_at = ?
        WHERE ticket_id = ?
        """,
        (
            timestamp,
            ticket_id,
        ),
    )

    conn.commit()
    conn.close()

    return parse_message_attachments(
        json.dumps(merged_records)
    )

# -----------------------------------
# RESET UNREAD
# -----------------------------------

def reset_unread(ticket_id):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tickets
        SET unread_count = 0
        WHERE ticket_id = ?
        """,
        (ticket_id,)
    )

    conn.commit()

    conn.close()

# -----------------------------------
# CLOSE TICKET
# -----------------------------------

def close_ticket(ticket_id):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tickets
        SET status = 'Closed',
            updated_at = ?
        WHERE ticket_id = ?
        """,
        (
            get_ticket_timestamp(),
            ticket_id,
        )
    )

    conn.commit()

    conn.close()

# -----------------------------------
# DELETE TICKET
# -----------------------------------

def delete_ticket(ticket_id):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM tickets
        WHERE ticket_id = ?
        """,
        (ticket_id,)
    )

    cursor.execute(
        """
        DELETE FROM messages
        WHERE ticket_id = ?
        """,
        (ticket_id,)
    )

    cursor.execute(
        """
        DELETE FROM ticket_notes
        WHERE ticket_id = ?
        """,
        (ticket_id,)
    )

    conn.commit()

    conn.close()

    remove_ticket_tag_links(ticket_id)


def reset_ticket_history():

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM messages
        """
    )

    cursor.execute(
        """
        DELETE FROM ticket_notes
        """
    )

    cursor.execute(
        """
        DELETE FROM tickets
        """
    )

    ensure_ticket_counter(cursor)

    cursor.execute(
        """
        UPDATE ticket_counters
        SET next_value = 1
        WHERE name = 'ticket_id'
        """
    )

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'sqlite_sequence'
        """
    )

    if cursor.fetchone():
        cursor.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name = 'messages'
            """
        )

    conn.commit()

    conn.close()
# -----------------------------------
# AI RECOMMENDATION
# -----------------------------------

def generate_ai_reply(issue):

    issue = str(issue or "").lower()

    if any(keyword in issue for keyword in ("payment", "invoice", "receipt", "emi")):
        return "We understand your payment concern. Our Acrobuild finance team is reviewing the transaction and will confirm the ledger status shortly."

    if any(keyword in issue for keyword in ("document", "agreement", "registration", "approval")):
        return "We are reviewing your documentation request. Please share the project and unit reference so the team can pull the correct record set."

    if any(keyword in issue for keyword in ("site visit", "visit", "inspection", "tour")):
        return "We can help arrange a site visit. Please share your preferred project, date, and contact number so our coordinator can confirm availability."

    if any(keyword in issue for keyword in ("maintenance", "handover", "possession", "defect", "leak")):
        return "We have logged your Acrobuild care request and the team will review the handover or maintenance details with priority."

    return "Thank you for contacting Acrobuild support. Our team is reviewing your request and will get back to you with the next step."

# -----------------------------------
# UPDATE TICKET AGENT
# -----------------------------------

def update_ticket_agent(ticket_id, agent_name):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tickets
        SET assigned_agent = ?,
            assignment_method = ?,
            updated_at = ?
        WHERE ticket_id = ?
        """,
        (
            agent_name,
            "Manual Reassignment",
            get_ticket_timestamp(),
            ticket_id,
        )
    )

    conn.commit()

    conn.close()

# -----------------------------------
# UPDATE TICKET STATUS
# -----------------------------------

def update_ticket_status(ticket_id, status):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tickets
        SET status = ?,
            updated_at = ?
        WHERE ticket_id = ?
        """,
        (
            status,
            get_ticket_timestamp(),
            ticket_id,
        )
    )

    conn.commit()

    conn.close()


# -----------------------------------
# SUPPORT USERS
# -----------------------------------

def get_support_users():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM support_users
        ORDER BY
            CASE role
                WHEN 'owner' THEN 0
                WHEN 'admin' THEN 1
                ELSE 2
            END,
            CASE status
                WHEN 'Active' THEN 0
                WHEN 'Invited' THEN 1
                ELSE 2
            END,
            name COLLATE NOCASE ASC
        """
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        dict(row)
        for row in rows
    ]


def create_support_user(
    name,
    email,
    role,
    team="Support",
    status="Invited",
    password="demo@123",
):

    timestamp = get_ticket_timestamp()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO support_users (
            name,
            email,
            role,
            team,
            status,
            password,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(name or "").strip(),
            str(email or "").strip().lower(),
            str(role or "agent").strip().lower(),
            str(team or "Support").strip() or "Support",
            str(status or "Invited").strip() or "Invited",
            str(password or "demo@123").strip() or "demo@123",
            timestamp,
            timestamp,
        )
    )

    user_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()

    return get_support_user(user_id)


def get_support_user(user_id):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM support_users
        WHERE id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return dict(row)


def update_support_user(
    user_id,
    name,
    role,
    team,
    status,
):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE support_users
        SET name = ?,
            role = ?,
            team = ?,
            status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(name or "").strip(),
            str(role or "agent").strip().lower(),
            str(team or "Support").strip() or "Support",
            str(status or "Active").strip() or "Active",
            get_ticket_timestamp(),
            user_id,
        )
    )

    conn.commit()
    conn.close()

    return get_support_user(user_id)


# -----------------------------------
# SUPPORT ARTICLES
# -----------------------------------

def normalize_support_article_row(row):

    article = dict(row)
    article["keywords"] = parse_json_string_list(
        article.get("keywords_json")
    )
    article.pop(
        "keywords_json",
        None,
    )

    return article


def get_support_articles():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM support_articles
        ORDER BY
            CASE status
                WHEN 'Published' THEN 0
                ELSE 1
            END,
            title COLLATE NOCASE ASC
        """
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        normalize_support_article_row(row)
        for row in rows
    ]


def get_support_article(article_id):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM support_articles
        WHERE id = ?
        """,
        (article_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return normalize_support_article_row(row)


def create_support_article(
    title,
    category="Support",
    status="Draft",
    summary="",
    body="",
    keywords=None,
    url="",
):

    timestamp = get_ticket_timestamp()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO support_articles (
            title,
            category,
            status,
            summary,
            body,
            keywords_json,
            url,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(title or "").strip() or "New article",
            str(category or "Support").strip() or "Support",
            str(status or "Draft").strip() or "Draft",
            str(summary or "").strip(),
            str(body or "").strip(),
            json.dumps(
                [
                    str(keyword).strip()
                    for keyword in (keywords or [])
                    if str(keyword).strip()
                ]
            ),
            str(url or "").strip(),
            timestamp,
            timestamp,
        )
    )

    article_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()

    return get_support_article(article_id)


def update_support_article(
    article_id,
    title,
    category,
    status,
    summary,
    body,
    keywords=None,
    url="",
):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE support_articles
        SET title = ?,
            category = ?,
            status = ?,
            summary = ?,
            body = ?,
            keywords_json = ?,
            url = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(title or "").strip() or "New article",
            str(category or "Support").strip() or "Support",
            str(status or "Draft").strip() or "Draft",
            str(summary or "").strip(),
            str(body or "").strip(),
            json.dumps(
                [
                    str(keyword).strip()
                    for keyword in (keywords or [])
                    if str(keyword).strip()
                ]
            ),
            str(url or "").strip(),
            get_ticket_timestamp(),
            article_id,
        )
    )

    conn.commit()
    conn.close()

    return get_support_article(article_id)


def reset_support_articles():

    conn = open_database_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM support_articles
        """
    )
    support_article_count = int(
        (cursor.fetchone() or [0])[0]
    )

    cursor.execute(
        """
        DELETE FROM support_articles
        """
    )

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'sqlite_sequence'
        """
    )

    if cursor.fetchone():
        cursor.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name = 'support_articles'
            """
        )

    conn.commit()
    conn.close()

    return {
        "deleted_support_articles": support_article_count,
    }


# -----------------------------------
# KNOWLEDGE DOCUMENTS
# -----------------------------------

def normalize_knowledge_document_row(row):

    document = dict(row)
    document["tags"] = parse_json_string_list(
        document.get("tags_json")
    )
    document.pop(
        "tags_json",
        None,
    )

    return document


def get_knowledge_documents():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM knowledge_documents
        ORDER BY
            CASE status
                WHEN 'Published' THEN 0
                ELSE 1
            END,
            updated_at DESC,
            title COLLATE NOCASE ASC
        """
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        normalize_knowledge_document_row(row)
        for row in rows
    ]


def get_knowledge_document(document_id):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM knowledge_documents
        WHERE id = ?
        """,
        (document_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return normalize_knowledge_document_row(row)


def create_knowledge_document(
    title,
    category="Knowledge",
    status="Draft",
    summary="",
    body="",
    tags=None,
    source_name="",
    source_type="manual",
):

    timestamp = get_ticket_timestamp()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO knowledge_documents (
            title,
            category,
            status,
            summary,
            body,
            tags_json,
            source_name,
            source_type,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(title or "").strip() or "New knowledge document",
            str(category or "Knowledge").strip() or "Knowledge",
            str(status or "Draft").strip() or "Draft",
            str(summary or "").strip(),
            str(body or "").strip(),
            json.dumps(
                [
                    str(tag).strip()
                    for tag in (tags or [])
                    if str(tag).strip()
                ]
            ),
            str(source_name or "").strip(),
            str(source_type or "manual").strip() or "manual",
            timestamp,
            timestamp,
        )
    )

    document_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()

    return get_knowledge_document(document_id)


def update_knowledge_document(
    document_id,
    title,
    category,
    status,
    summary,
    body,
    tags=None,
    source_name="",
    source_type="manual",
):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE knowledge_documents
        SET title = ?,
            category = ?,
            status = ?,
            summary = ?,
            body = ?,
            tags_json = ?,
            source_name = ?,
            source_type = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(title or "").strip() or "New knowledge document",
            str(category or "Knowledge").strip() or "Knowledge",
            str(status or "Draft").strip() or "Draft",
            str(summary or "").strip(),
            str(body or "").strip(),
            json.dumps(
                [
                    str(tag).strip()
                    for tag in (tags or [])
                    if str(tag).strip()
                ]
            ),
            str(source_name or "").strip(),
            str(source_type or "manual").strip() or "manual",
            get_ticket_timestamp(),
            document_id,
        )
    )

    conn.commit()
    conn.close()

    return get_knowledge_document(document_id)


def delete_knowledge_documents(
    document_ids,
):

    normalized_document_ids = sorted(
        {
            int(document_id)
            for document_id in (
                document_ids or []
            )
            if str(document_id).strip()
        }
    )

    if not normalized_document_ids:
        return {
            "deleted_count": 0,
            "deleted_ids": [],
        }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    placeholders = ",".join(
        "?"
        for _ in normalized_document_ids
    )

    cursor.execute(
        f"""
        DELETE FROM knowledge_documents
        WHERE id IN ({placeholders})
        """,
        tuple(normalized_document_ids),
    )

    deleted_count = int(
        cursor.rowcount or 0
    )
    conn.commit()
    conn.close()

    return {
        "deleted_count": deleted_count,
        "deleted_ids": normalized_document_ids,
    }


def reset_knowledge_documents():

    conn = open_database_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM knowledge_documents
        """
    )
    knowledge_document_count = int(
        (cursor.fetchone() or [0])[0]
    )

    cursor.execute(
        """
        DELETE FROM knowledge_documents
        """
    )

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'sqlite_sequence'
        """
    )

    if cursor.fetchone():
        cursor.execute(
            """
            DELETE FROM sqlite_sequence
            WHERE name = 'knowledge_documents'
            """
        )

    conn.commit()
    conn.close()

    return {
        "deleted_knowledge_documents": knowledge_document_count,
    }


def reset_workspace_knowledge():

    support_article_result = (
        reset_support_articles()
    )
    knowledge_document_result = (
        reset_knowledge_documents()
    )

    return {
        **support_article_result,
        **knowledge_document_result,
    }
