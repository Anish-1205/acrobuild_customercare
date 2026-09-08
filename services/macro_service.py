import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = str(
    Path(__file__).resolve().parent.parent
    / "support_system.db"
)

MACRO_STORE_READY = False
MACRO_STORE_INITIALIZING = False

DEFAULT_MACRO_LANGUAGE = "English"
DEFAULT_MACRO_STATUS = ""

DEFAULT_MACROS = [
    {
        "name": "Site Visit Confirmation",
        "language": "English",
        "category": "Site Visit",
        "response_text": (
            "Hi {{ customer_first_name }},\n\n"
            "Thanks for your interest in Acrobuild. We can help arrange a site visit for ticket {{ ticket_id }}. "
            "Please reply with your preferred project, date, time window, and the best contact number for the visit coordinator.\n\n"
            "Once we have that, our site operations team will confirm the slot and share the visit details with you.\n\n"
            "Best regards,\n"
            "{{ agent_first_name }}"
        ),
        "tag_names": [
            "Site Visit",
            "visit_request",
        ],
        "subject_template": "Acrobuild Site Visit Request",
        "set_status": "Waiting on Customer",
    },
    {
        "name": "Quotation Follow-Up",
        "language": "English",
        "category": "Sales",
        "response_text": (
            "Hi {{ customer_first_name }},\n\n"
            "We are preparing the latest quotation linked to ticket {{ ticket_id }}. "
            "If you already know the project, unit preference, budget range, or configuration you want, reply here and we will tailor the proposal accordingly.\n\n"
            "Our sales advisory team will share the next update as soon as the pricing and availability check is complete.\n\n"
            "Best regards,\n"
            "{{ agent_first_name }}"
        ),
        "tag_names": [
            "Quotation",
            "inventory_check",
        ],
        "subject_template": "Acrobuild Quotation Follow-Up",
        "set_status": "In Progress",
    },
    {
        "name": "Payment Receipt Acknowledgement",
        "language": "English",
        "category": "Payments",
        "response_text": (
            "Hi {{ customer_first_name }},\n\n"
            "We have received your payment query for ticket {{ ticket_id }}. "
            "Please reply with the transaction reference, payment date, amount paid, and the project or unit reference so our finance team can reconcile it quickly.\n\n"
            "Once the payment is matched in the ledger, we will confirm the receipt or advise the next step.\n\n"
            "Best regards,\n"
            "{{ agent_first_name }}"
        ),
        "tag_names": [
            "Payment",
            "receipt_check",
        ],
        "subject_template": "Acrobuild Payment Update",
        "set_status": "Waiting on Customer",
    },
    {
        "name": "Construction Update Pending",
        "language": "English",
        "category": "Construction",
        "response_text": (
            "Hi {{ customer_first_name }},\n\n"
            "Thanks for reaching out about the project progress. We have flagged ticket {{ ticket_id }} with the site operations team for the latest construction update.\n\n"
            "If you already have the tower, phase, or unit reference, reply here and we will include it with the follow-up so the team can check the right milestone.\n\n"
            "Best regards,\n"
            "{{ agent_first_name }}"
        ),
        "tag_names": [
            "Construction",
            "progress_update",
        ],
        "subject_template": "Construction Progress Update",
        "set_status": "In Progress",
    },
    {
        "name": "Document Checklist Request",
        "language": "English",
        "category": "Documentation",
        "response_text": (
            "Hi {{ customer_first_name }},\n\n"
            "We can help with the documentation request linked to ticket {{ ticket_id }}. "
            "Please share the project name, booking or unit reference, and the specific document you need so our documentation desk can verify the file set.\n\n"
            "If any KYC or authorization step is still pending, we will outline that clearly in the next update.\n\n"
            "Best regards,\n"
            "{{ agent_first_name }}"
        ),
        "tag_names": [
            "Documents",
            "kyc",
        ],
        "subject_template": "Acrobuild Documentation Request",
        "set_status": "Waiting on Customer",
    },
    {
        "name": "Handover Defect Acknowledgement",
        "language": "English",
        "category": "Maintenance",
        "response_text": (
            "Hi {{ customer_first_name }},\n\n"
            "We are sorry to hear about the handover or maintenance issue. We have logged ticket {{ ticket_id }} with the Acrobuild care team for review.\n\n"
            "Please reply with the project name, tower or unit number, and clear photos or videos of the issue if available so we can guide the next action quickly.\n\n"
            "Best regards,\n"
            "{{ agent_first_name }}"
        ),
        "tag_names": [
            "Handover",
            "defect_report",
        ],
        "subject_template": "Acrobuild Care Team Update",
        "set_status": "In Progress",
    },
]

LEGACY_DEFAULT_MACRO_SHORTCUTS = {
    "confirmation-of-refund",
    "delivery-delayed-response",
    "missing-meals-response",
    "replacement-meals-update",
    "request-to-update-address",
    "wrong-meals-response",
}


# -----------------------------------
# INTERNAL HELPERS
# -----------------------------------
def get_connection():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    return conn


def get_timestamp():

    return datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")


def row_to_dict(row):

    if row is None:
        return None

    return dict(row)


def slugify_value(value):

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        str(value or "").strip().lower(),
    ).strip("-") or "macro"


def normalize_macro_tag_names(tag_names):

    cleaned_tags = []
    seen = set()

    for tag_name in tag_names or []:
        cleaned_tag = str(
            tag_name or ""
        ).strip()

        if not cleaned_tag:
            continue

        normalized_tag = (
            cleaned_tag.lower()
        )

        if normalized_tag in seen:
            continue

        seen.add(normalized_tag)
        cleaned_tags.append(cleaned_tag)

    return cleaned_tags


def ensure_column(
    cursor,
    table_name,
    column_name,
    column_definition,
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


def build_unique_shortcut(
    conn,
    value,
    macro_id=None,
):

    cursor = conn.cursor()
    base_shortcut = slugify_value(value)
    shortcut = base_shortcut
    copy_index = 2

    while True:
        if macro_id is None:
            cursor.execute(
                """
                SELECT id
                FROM macros
                WHERE shortcut = ?
                """,
                (shortcut,)
            )
        else:
            cursor.execute(
                """
                SELECT id
                FROM macros
                WHERE shortcut = ?
                  AND id != ?
                """,
                (
                    shortcut,
                    macro_id,
                )
            )

        if cursor.fetchone() is None:
            return shortcut

        shortcut = (
            f"{base_shortcut}-{copy_index}"
        )
        copy_index += 1


def save_macro_tag_names(
    conn,
    macro_id,
    tag_names,
):

    cursor = conn.cursor()
    normalized_tag_names = (
        normalize_macro_tag_names(tag_names)
    )

    cursor.execute(
        """
        DELETE FROM macro_tags
        WHERE macro_id = ?
        """,
        (macro_id,)
    )

    timestamp = get_timestamp()

    for tag_name in normalized_tag_names:
        cursor.execute(
            """
            INSERT OR IGNORE INTO macro_tags (
                macro_id,
                tag_name,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                macro_id,
                tag_name,
                timestamp,
            )
        )


def load_macro_tag_names(
    conn,
    macro_ids,
):

    if not macro_ids:
        return {}

    cursor = conn.cursor()
    placeholders = ",".join(
        "?"
        for _ in macro_ids
    )
    cursor.execute(
        f"""
        SELECT macro_id,
               tag_name
        FROM macro_tags
        WHERE macro_id IN ({placeholders})
        ORDER BY tag_name COLLATE NOCASE ASC
        """,
        tuple(macro_ids),
    )

    tag_map = {
        int(macro_id): []
        for macro_id in macro_ids
    }

    for row in cursor.fetchall():
        tag_map[
            int(row["macro_id"])
        ].append(row["tag_name"])

    return tag_map


def hydrate_macros(
    conn,
    rows,
):

    macro_rows = [
        row_to_dict(row)
        for row in rows
    ]
    tag_map = load_macro_tag_names(
        conn,
        [
            int(macro["id"])
            for macro in macro_rows
        ],
    )

    for macro in macro_rows:
        macro["tag_names"] = tag_map.get(
            int(macro["id"]),
            [],
        )

    return macro_rows


def upsert_seed_macro(
    conn,
    macro,
):

    cursor = conn.cursor()
    timestamp = get_timestamp()
    shortcut = slugify_value(
        macro.get("name")
    )

    cursor.execute(
        """
        SELECT id
        FROM macros
        WHERE shortcut = ?
        """,
        (shortcut,)
    )

    existing_row = cursor.fetchone()

    if existing_row:
        return int(existing_row["id"])

    cursor.execute(
        """
        INSERT INTO macros (
            name,
            slug,
            shortcut,
            language,
            response_text,
            description,
            category,
            subject_template,
            set_status,
            is_archived,
            usage_count,
            created_at,
            updated_at,
            last_used_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, NULL)
        """,
        (
            macro.get("name"),
            slugify_value(
                macro.get("name")
            ),
            shortcut,
            macro.get(
                "language",
                DEFAULT_MACRO_LANGUAGE,
            ),
            macro.get(
                "response_text",
                "",
            ),
            macro.get(
                "description",
                "",
            ),
            macro.get(
                "category",
                "",
            ),
            macro.get(
                "subject_template",
                "",
            ),
            macro.get(
                "set_status",
                DEFAULT_MACRO_STATUS,
            ),
            timestamp,
            timestamp,
        )
    )

    macro_id = int(cursor.lastrowid)
    save_macro_tag_names(
        conn,
        macro_id,
        macro.get(
            "tag_names",
            [],
        ),
    )

    return macro_id


def archive_legacy_default_macros(conn):

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE macros
        SET is_archived = 1
        WHERE shortcut IN (?, ?, ?, ?, ?, ?)
        """,
        tuple(sorted(LEGACY_DEFAULT_MACRO_SHORTCUTS)),
    )


def ensure_default_macros(conn):

    archive_legacy_default_macros(conn)

    for macro in DEFAULT_MACROS:
        upsert_seed_macro(
            conn,
            macro,
        )


def normalize_macro_for_search(macro):

    return " ".join(
        [
            str(
                macro.get("name", "")
            ).lower(),
            str(
                macro.get("shortcut", "")
            ).lower(),
            str(
                macro.get("response_text", "")
            ).lower(),
            str(
                macro.get(
                    "subject_template",
                    "",
                )
            ).lower(),
            str(
                macro.get("category", "")
            ).lower(),
            " ".join(
                tag.lower()
                for tag in macro.get(
                    "tag_names",
                    [],
                )
            ),
        ]
    )


def normalize_match_value(value):

    cleaned_value = str(
        value or ""
    ).strip()

    if not cleaned_value:
        return ""

    return slugify_value(cleaned_value).replace(
        "-",
        " ",
    )


# -----------------------------------
# INITIALIZATION
# -----------------------------------

def initialize_macro_store():

    global MACRO_STORE_INITIALIZING
    global MACRO_STORE_READY

    if MACRO_STORE_READY:
        return

    if MACRO_STORE_INITIALIZING:
        return

    MACRO_STORE_INITIALIZING = True

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS macros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                shortcut TEXT NOT NULL UNIQUE,
                language TEXT NOT NULL DEFAULT 'English',
                response_text TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                subject_template TEXT DEFAULT '',
                set_status TEXT DEFAULT '',
                is_archived INTEGER NOT NULL DEFAULT 0,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_used_at TEXT
            )
            """
        )

        ensure_column(
            cursor,
            "macros",
            "slug",
            "TEXT NOT NULL DEFAULT 'macro'",
        )
        ensure_column(
            cursor,
            "macros",
            "shortcut",
            "TEXT NOT NULL DEFAULT 'macro'",
        )
        ensure_column(
            cursor,
            "macros",
            "language",
            "TEXT NOT NULL DEFAULT 'English'",
        )
        ensure_column(
            cursor,
            "macros",
            "description",
            "TEXT DEFAULT ''",
        )
        ensure_column(
            cursor,
            "macros",
            "category",
            "TEXT DEFAULT ''",
        )
        ensure_column(
            cursor,
            "macros",
            "subject_template",
            "TEXT DEFAULT ''",
        )
        ensure_column(
            cursor,
            "macros",
            "set_status",
            "TEXT DEFAULT ''",
        )
        ensure_column(
            cursor,
            "macros",
            "is_archived",
            "INTEGER NOT NULL DEFAULT 0",
        )
        ensure_column(
            cursor,
            "macros",
            "usage_count",
            "INTEGER NOT NULL DEFAULT 0",
        )
        ensure_column(
            cursor,
            "macros",
            "last_used_at",
            "TEXT",
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS macro_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                macro_id INTEGER NOT NULL,
                tag_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(macro_id, tag_name)
            )
            """
        )

        ensure_default_macros(conn)
        conn.commit()
        conn.close()
        MACRO_STORE_READY = True
    finally:
        MACRO_STORE_INITIALIZING = False


# -----------------------------------
# CRUD
# -----------------------------------

def get_macros(
    search_term="",
    language=None,
    category=None,
    tag_name=None,
    include_archived=False,
):

    initialize_macro_store()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM macros
        ORDER BY is_archived ASC,
                 updated_at DESC,
                 name COLLATE NOCASE ASC
        """
    )

    macros = hydrate_macros(
        conn,
        cursor.fetchall(),
    )
    conn.close()

    search_text = str(
        search_term or ""
    ).strip().lower()
    language_text = str(
        language or ""
    ).strip().lower()
    category_text = str(
        category or ""
    ).strip().lower()
    tag_text = str(
        tag_name or ""
    ).strip().lower()

    filtered_macros = []

    for macro in macros:
        if not include_archived and int(
            macro.get("is_archived", 0)
        ):
            continue

        if (
            language_text
            and language_text != "all"
            and str(
                macro.get("language", "")
            ).strip().lower()
            != language_text
        ):
            continue

        if (
            category_text
            and category_text != "all"
            and str(
                macro.get("category", "")
            ).strip().lower()
            != category_text
        ):
            continue

        if tag_text and not any(
            tag_text in tag.lower()
            for tag in macro.get(
                "tag_names",
                [],
            )
        ):
            continue

        if search_text and search_text not in (
            normalize_macro_for_search(
                macro
            )
        ):
            continue

        filtered_macros.append(macro)

    return filtered_macros


def get_macro(macro_id):

    initialize_macro_store()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM macros
        WHERE id = ?
        """,
        (macro_id,)
    )

    macros = hydrate_macros(
        conn,
        cursor.fetchall(),
    )
    conn.close()

    return macros[0] if macros else None


def create_macro(
    name,
    response_text,
    language=DEFAULT_MACRO_LANGUAGE,
    description="",
    category="",
    subject_template="",
    set_status=DEFAULT_MACRO_STATUS,
    tag_names=None,
):

    initialize_macro_store()

    cleaned_name = str(
        name or ""
    ).strip()
    cleaned_response = str(
        response_text or ""
    ).strip()

    if not cleaned_name:
        raise ValueError(
            "Macro name is required."
        )

    if not cleaned_response:
        raise ValueError(
            "Response text is required."
        )

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    shortcut = build_unique_shortcut(
        conn,
        cleaned_name,
    )

    cursor.execute(
        """
        INSERT INTO macros (
            name,
            slug,
            shortcut,
            language,
            response_text,
            description,
            category,
            subject_template,
            set_status,
            is_archived,
            usage_count,
            created_at,
            updated_at,
            last_used_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, NULL)
        """,
        (
            cleaned_name,
            slugify_value(
                cleaned_name
            ),
            shortcut,
            str(language or "").strip()
            or DEFAULT_MACRO_LANGUAGE,
            cleaned_response,
            str(description or "").strip(),
            str(category or "").strip(),
            str(subject_template or "").strip(),
            str(set_status or "").strip(),
            timestamp,
            timestamp,
        )
    )

    macro_id = int(cursor.lastrowid)
    save_macro_tag_names(
        conn,
        macro_id,
        tag_names or [],
    )

    conn.commit()
    conn.close()

    return macro_id


def update_macro(
    macro_id,
    name,
    response_text,
    language=DEFAULT_MACRO_LANGUAGE,
    description="",
    category="",
    subject_template="",
    set_status=DEFAULT_MACRO_STATUS,
    tag_names=None,
):

    initialize_macro_store()

    existing_macro = get_macro(
        macro_id
    )

    if existing_macro is None:
        raise ValueError(
            "Macro not found."
        )

    cleaned_name = str(
        name or ""
    ).strip()
    cleaned_response = str(
        response_text or ""
    ).strip()

    if not cleaned_name:
        raise ValueError(
            "Macro name is required."
        )

    if not cleaned_response:
        raise ValueError(
            "Response text is required."
        )

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    shortcut = build_unique_shortcut(
        conn,
        cleaned_name,
        macro_id=macro_id,
    )

    cursor.execute(
        """
        UPDATE macros
        SET name = ?,
            slug = ?,
            shortcut = ?,
            language = ?,
            response_text = ?,
            description = ?,
            category = ?,
            subject_template = ?,
            set_status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            cleaned_name,
            slugify_value(
                cleaned_name
            ),
            shortcut,
            str(language or "").strip()
            or DEFAULT_MACRO_LANGUAGE,
            cleaned_response,
            str(description or "").strip(),
            str(category or "").strip(),
            str(subject_template or "").strip(),
            str(set_status or "").strip(),
            timestamp,
            macro_id,
        )
    )

    save_macro_tag_names(
        conn,
        macro_id,
        tag_names or [],
    )

    conn.commit()
    conn.close()


def duplicate_macro(macro_id):

    initialize_macro_store()

    macro = get_macro(
        macro_id
    )

    if macro is None:
        raise ValueError(
            "Macro not found."
        )

    duplicate_name = (
        f"{macro['name']} Copy"
    )

    return create_macro(
        name=duplicate_name,
        response_text=macro.get(
            "response_text",
            "",
        ),
        language=macro.get(
            "language",
            DEFAULT_MACRO_LANGUAGE,
        ),
        description=macro.get(
            "description",
            "",
        ),
        category=macro.get(
            "category",
            "",
        ),
        subject_template=macro.get(
            "subject_template",
            "",
        ),
        set_status=macro.get(
            "set_status",
            DEFAULT_MACRO_STATUS,
        ),
        tag_names=macro.get(
            "tag_names",
            [],
        ),
    )


def archive_macro(
    macro_id,
    is_archived=True,
):

    initialize_macro_store()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE macros
        SET is_archived = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            1 if is_archived else 0,
            get_timestamp(),
            macro_id,
        )
    )

    conn.commit()
    conn.close()


def delete_macro(macro_id):

    initialize_macro_store()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM macro_tags
        WHERE macro_id = ?
        """,
        (macro_id,)
    )
    cursor.execute(
        """
        DELETE FROM macros
        WHERE id = ?
        """,
        (macro_id,)
    )

    conn.commit()
    conn.close()


def increment_macro_usage(macro_id):

    initialize_macro_store()

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    cursor.execute(
        """
        UPDATE macros
        SET usage_count = usage_count + 1,
            last_used_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            timestamp,
            timestamp,
            macro_id,
        )
    )

    conn.commit()
    conn.close()


# -----------------------------------
# TEMPLATE HELPERS
# -----------------------------------

def render_macro_template(
    template,
    variables,
):

    variable_map = {
        str(key).strip().lower(): str(
            value or ""
        )
        for key, value in (
            variables or {}
        ).items()
    }

    def replace_match(match):
        variable_name = match.group(1).strip().lower()
        return variable_map.get(
            variable_name,
            "",
        )

    return re.sub(
        r"\{\{\s*([^}]+?)\s*\}\}",
        replace_match,
        str(template or ""),
    )


def score_macro_for_ticket(
    macro,
    ticket,
    ticket_tag_names=None,
):

    issue_type = normalize_match_value(
        ticket.get("issue_type")
    )
    intent_tag = normalize_match_value(
        ticket.get("intent_tag")
    )
    queue_name = normalize_match_value(
        ticket.get("queue_name")
    )

    macro_category = normalize_match_value(
        macro.get("category")
    )
    macro_tags = {
        normalize_match_value(tag_name)
        for tag_name in macro.get(
            "tag_names",
            [],
        )
    }
    ticket_tags = {
        normalize_match_value(tag_name)
        for tag_name in (
            ticket_tag_names or []
        )
    }

    score = 0

    if macro_category and macro_category == issue_type:
        score += 18

    if issue_type and issue_type in macro_tags:
        score += 10

    if intent_tag and intent_tag in macro_tags:
        score += 8

    if queue_name and queue_name in macro_tags:
        score += 5

    score += (
        len(macro_tags & ticket_tags)
        * 7
    )

    issue_text = normalize_macro_for_search(
        {
            "name": ticket.get("issue", ""),
            "shortcut": "",
            "response_text": "",
            "subject_template": "",
            "category": ticket.get(
                "issue_type",
                "",
            ),
            "tag_names": ticket_tag_names or [],
        }
    )

    macro_text = normalize_macro_for_search(
        macro
    )

    if issue_text:
        issue_words = {
            word
            for word in issue_text.split()
            if len(word) > 3
        }
        macro_words = set(
            macro_text.split()
        )
        score += len(
            issue_words & macro_words
        )

    return score


def get_recommended_macros_for_ticket(
    ticket,
    ticket_tag_names=None,
    limit=None,
):

    macros = get_macros(
        include_archived=False
    )
    scored_macros = []

    for macro in macros:
        score = score_macro_for_ticket(
            macro,
            ticket,
            ticket_tag_names=ticket_tag_names,
        )
        scored_macros.append(
            (
                score,
                int(
                    macro.get(
                        "usage_count",
                        0,
                    )
                    or 0
                ),
                macro,
            )
        )

    scored_macros.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2].get(
                "updated_at",
                "",
            ),
        ),
        reverse=True,
    )

    ordered_macros = [
        macro
        for score, _, macro in scored_macros
        if score > 0
    ]

    if not ordered_macros:
        ordered_macros = [
            macro
            for _, _, macro in scored_macros
        ]

    if limit is None:
        return ordered_macros

    return ordered_macros[:limit]
