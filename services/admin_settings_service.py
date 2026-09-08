import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


DB_PATH = str(
    Path(__file__).resolve().parent.parent
    / "support_system.db"
)

DEFAULT_TIMEZONE = os.getenv(
    "SUPPORT_TIMEZONE",
    "Australia/Sydney",
).strip() or "Australia/Sydney"

DEFAULT_START_HOUR = int(
    os.getenv(
        "SUPPORT_BUSINESS_HOURS_START",
        "9",
    )
)

DEFAULT_END_HOUR = int(
    os.getenv(
        "SUPPORT_BUSINESS_HOURS_END",
        "21",
    )
)

DEFAULT_RULE_KEY = "tag_tickets_by_business_hours"
ADMIN_SETTINGS_READY = False
ADMIN_SETTINGS_INITIALIZING = False

RULE_MODE_BUSINESS_HOURS = "business_hours"
RULE_MODE_CUSTOM = "custom"

RULE_ALLOWED_FIELDS = {
    "assigned_agent",
    "created_at",
    "customer_email",
    "customer_order_count",
    "customer_total_spent",
    "customer_vip",
    "issue_type",
    "message_from_agent",
    "priority",
    "ticket_status",
}

RULE_BOOLEAN_FIELDS = {
    "customer_vip",
    "message_from_agent",
}

RULE_NUMERIC_FIELDS = {
    "customer_order_count",
    "customer_total_spent",
}

RULE_CUSTOMER_PROFILE_FIELDS = {
    "customer_order_count",
    "customer_total_spent",
    "customer_vip",
}

RULE_TEXT_FIELDS = {
    "assigned_agent",
    "customer_email",
    "issue_type",
    "priority",
    "ticket_status",
}

DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

DAY_NAME_TO_INDEX = {
    day_name: index
    for index, day_name in enumerate(
        DAY_NAMES
    )
}

TAG_COLOR_PALETTE = [
    "#38bdf8",
    "#2563eb",
    "#1d4ed8",
    "#14b8a6",
    "#a3a3a3",
    "#6b7280",
    "#52525b",
    "#4ade80",
    "#556b2f",
    "#f97316",
]

DEFAULT_TAGS = [
    {
        "name": "During Business Hours",
        "description": "Applied when a ticket is created during business hours.",
        "color": "#38bdf8",
    },
    {
        "name": "Outside Business Hours",
        "description": "Applied when a ticket is created outside the default schedule.",
        "color": "#2563eb",
    },
    {
        "name": "Auto Close",
        "description": "Marks requests that can be handled by automated follow-up.",
        "color": "#1d4ed8",
    },
    {
        "name": "Non Support Related",
        "description": "Highlights tickets that are not support requests.",
        "color": "#14b8a6",
    },
    {
        "name": "Urgent",
        "description": "Escalation tag for time-sensitive customer issues.",
        "color": "#a3a3a3",
    },
    {
        "name": "Site Visit",
        "description": "Used for customers asking to schedule or update a property visit.",
        "color": "#6b7280",
    },
    {
        "name": "Quotation",
        "description": "Highlights requests for pricing, estimates, and availability.",
        "color": "#52525b",
    },
    {
        "name": "Construction Update",
        "description": "Tracks build progress, milestone, and timeline-related conversations.",
        "color": "#4ade80",
    },
    {
        "name": "Documentation",
        "description": "Used for legal paperwork, approvals, and account access support.",
        "color": "#556b2f",
    },
    {
        "name": "Handover",
        "description": "Applied to possession, key handover, and move-in support requests.",
        "color": "#f97316",
    },
    {
        "name": "Maintenance",
        "description": "Used for defect reporting, repair coordination, and after-sales care.",
        "color": "#38bdf8",
    },
    {
        "name": "Payment Follow Up",
        "description": "Tracks payment plan, invoice, and outstanding balance conversations.",
        "color": "#2563eb",
    },
    {
        "name": "Priority Buyer",
        "description": "Flags high-value buyers and priority relationship accounts.",
        "color": "#14b8a6",
    },
]

LEGACY_DEFAULT_TAG_SLUGS = {
    "cancel",
    "order-cancellation",
    "subscription",
    "vip",
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


def slugify_tag_name(value):

    normalized = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(value or "").strip().lower(),
    ).strip("-")

    return normalized or "tag"


def normalize_color(
    value,
    fallback_color="#38bdf8",
):

    color = str(value or "").strip()

    if re.fullmatch(
        r"#[0-9a-fA-F]{6}",
        color,
    ):
        return color.lower()

    return fallback_color.lower()


def normalize_time_string(value):

    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")

    text = str(value or "").strip()

    if not text:
        return "09:00"

    if len(text) >= 5 and text[2] == ":":
        return text[:5]

    return "09:00"


def parse_time_string(value):

    normalized = normalize_time_string(value)

    return datetime.strptime(
        normalized,
        "%H:%M",
    ).time()


def get_timezone(timezone_name):

    try:
        return ZoneInfo(
            timezone_name
        )

    except Exception:
        return ZoneInfo("UTC")


def parse_reference_datetime(
    value,
    timezone_name=None,
):

    if timezone_name is None:
        timezone_name = DEFAULT_TIMEZONE

    target_timezone = get_timezone(
        timezone_name
    )

    if isinstance(value, datetime):
        reference_time = value

    else:
        reference_text = str(
            value or ""
        ).strip()

        if not reference_text:
            reference_time = datetime.now(
                target_timezone
            )

        else:
            try:
                reference_time = datetime.fromisoformat(
                    reference_text.replace(
                        "Z",
                        "+00:00",
                    )
                )

            except ValueError:
                for timestamp_format in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                ):
                    try:
                        reference_time = datetime.strptime(
                            reference_text,
                            timestamp_format,
                        )
                        break

                    except ValueError:
                        reference_time = None

                if reference_time is None:
                    reference_time = datetime.now(
                        target_timezone
                    )

    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(
            tzinfo=target_timezone
        )

    return reference_time.astimezone(
        target_timezone
    )


def sort_ranges(ranges):

    return sorted(
        [
            {
                "day_name": (
                    range_item.get("day_name")
                    or "Monday"
                ),
                "start_time": normalize_time_string(
                    range_item.get("start_time")
                ),
                "end_time": normalize_time_string(
                    range_item.get("end_time")
                ),
            }
            for range_item in ranges
            if range_item.get("day_name")
        ],
        key=lambda range_item: (
            DAY_NAME_TO_INDEX.get(
                range_item["day_name"],
                99,
            ),
            range_item["start_time"],
            range_item["end_time"],
        ),
    )


def build_schedule_summary(ranges):

    normalized_ranges = sort_ranges(
        ranges
    )

    if not normalized_ranges:
        return "No business hours configured"

    segments = [
        (
            f"{range_item['day_name']}, "
            f"{range_item['start_time']}"
            f"-{range_item['end_time']}"
        )
        for range_item in normalized_ranges
    ]

    if len(segments) <= 3:
        return " | ".join(segments)

    return (
        " | ".join(segments[:3])
        + " | ..."
    )


def build_default_ranges():

    start_time = f"{DEFAULT_START_HOUR:02d}:00"
    end_time = f"{DEFAULT_END_HOUR:02d}:00"

    return [
        {
            "day_name": day_name,
            "start_time": start_time,
            "end_time": end_time,
        }
        for day_name in DAY_NAMES[:5]
    ]


def row_to_dict(row):

    if row is None:
        return None

    return dict(row)


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
        row["name"]
        if isinstance(row, sqlite3.Row)
        else row[1]
        for row in cursor.fetchall()
    }

    if column_name not in columns:
        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {column_definition}
            """
        )


def normalize_rule_text(
    value,
    fallback="",
):

    text = str(value or "").strip()

    return text or fallback


def parse_float_value(value, fallback=0.0):

    try:
        return float(
            str(value or "").strip()
        )
    except (TypeError, ValueError):
        return float(fallback)


def parse_int_value(value, fallback=0):

    try:
        return int(
            float(
                str(value or "").strip()
            )
        )
    except (TypeError, ValueError):
        return int(fallback)


def normalize_rule_tag_ids(tag_ids):

    if not isinstance(tag_ids, list):
        return []

    normalized_ids = []
    seen_ids = set()

    for tag_id in tag_ids:
        normalized_tag_id = parse_int_value(
            tag_id,
            fallback=0,
        )

        if normalized_tag_id <= 0:
            continue

        if normalized_tag_id in seen_ids:
            continue

        seen_ids.add(normalized_tag_id)
        normalized_ids.append(
            normalized_tag_id
        )

    return normalized_ids


def build_business_hours_rule_config(
    match_tag_ids=None,
    else_tag_ids=None,
):

    return {
        "version": 1,
        "mode": RULE_MODE_BUSINESS_HOURS,
        "event": "ticket_created",
        "trigger_conditions": [
            {
                "id": "trigger-1",
                "field": "created_at",
                "operator": "during_business_hours",
                "value": "",
            }
        ],
        "branch_conditions": [],
        "match_tag_ids": normalize_rule_tag_ids(
            match_tag_ids or []
        ),
        "else_tag_ids": normalize_rule_tag_ids(
            else_tag_ids or []
        ),
    }


def build_default_custom_rule_config(
    match_tag_ids=None,
    else_tag_ids=None,
):

    return {
        "version": 1,
        "mode": RULE_MODE_CUSTOM,
        "event": "ticket_created",
        "trigger_conditions": [
            {
                "id": "trigger-1",
                "field": "ticket_status",
                "operator": "is",
                "value": "Open",
            },
            {
                "id": "trigger-2",
                "field": "message_from_agent",
                "operator": "is",
                "value": "false",
            },
        ],
        "branch_conditions": [
            {
                "id": "branch-1",
                "field": "customer_total_spent",
                "operator": "greater_or_equal",
                "value": "1000",
            }
        ],
        "match_tag_ids": normalize_rule_tag_ids(
            match_tag_ids or []
        ),
        "else_tag_ids": normalize_rule_tag_ids(
            else_tag_ids or []
        ),
    }


def normalize_rule_condition(
    condition,
    index=0,
):

    source = condition if isinstance(
        condition,
        dict,
    ) else {}

    field_name = normalize_rule_text(
        source.get("field"),
        "ticket_status",
    )

    if field_name not in RULE_ALLOWED_FIELDS:
        field_name = "ticket_status"

    operator = normalize_rule_text(
        source.get("operator"),
        "is",
    )
    raw_value = source.get("value")

    if field_name == "created_at":
        if operator not in (
            "during_business_hours",
            "outside_business_hours",
        ):
            operator = "during_business_hours"

        normalized_value = ""

    elif field_name in RULE_NUMERIC_FIELDS:
        if operator not in (
            "greater_or_equal",
            "greater_than",
            "less_or_equal",
            "less_than",
            "is",
            "is_not",
        ):
            operator = "greater_or_equal"

        normalized_value = str(
            parse_float_value(
                raw_value,
                fallback=0,
            )
        ).rstrip("0").rstrip(".")

        if not normalized_value:
            normalized_value = "0"

    elif field_name in RULE_BOOLEAN_FIELDS:
        if operator not in (
            "is",
            "is_not",
        ):
            operator = "is"

        normalized_value = (
            "true"
            if str(raw_value).strip().lower()
            in (
                "1",
                "true",
                "yes",
            )
            else "false"
        )

    else:
        if operator not in (
            "is",
            "is_not",
            "contains",
            "not_contains",
        ):
            operator = "is"

        normalized_value = normalize_rule_text(
            raw_value,
            "",
        )

    return {
        "id": normalize_rule_text(
            source.get("id"),
            f"condition-{index + 1}",
        ),
        "field": field_name,
        "operator": operator,
        "value": normalized_value,
    }


def normalize_rule_config(
    config,
    legacy_rule=None,
):

    parsed_config = {}

    if isinstance(config, dict):
        parsed_config = config

    elif isinstance(config, str):
        try:
            loaded_config = json.loads(
                config
            )

            if isinstance(loaded_config, dict):
                parsed_config = loaded_config
        except json.JSONDecodeError:
            parsed_config = {}

    legacy_true_tag_ids = []
    legacy_false_tag_ids = []
    legacy_mode = RULE_MODE_CUSTOM
    legacy_event_name = "ticket_created"

    if isinstance(legacy_rule, dict):
        legacy_event_name = normalize_rule_text(
            legacy_rule.get("event_name"),
            "ticket_created",
        )

        if legacy_rule.get("true_tag_id"):
            legacy_true_tag_ids = [
                parse_int_value(
                    legacy_rule.get(
                        "true_tag_id"
                    ),
                    fallback=0,
                )
            ]

        if legacy_rule.get("false_tag_id"):
            legacy_false_tag_ids = [
                parse_int_value(
                    legacy_rule.get(
                        "false_tag_id"
                    ),
                    fallback=0,
                )
            ]

        if normalize_rule_text(
            legacy_rule.get(
                "builder_mode"
            ),
            "",
        ) == RULE_MODE_BUSINESS_HOURS or normalize_rule_text(
            legacy_rule.get(
                "condition_operator"
            ),
            "",
        ) == "during_business_hours":
            legacy_mode = RULE_MODE_BUSINESS_HOURS

    mode = normalize_rule_text(
        parsed_config.get("mode"),
        legacy_mode,
    )

    if mode not in (
        RULE_MODE_BUSINESS_HOURS,
        RULE_MODE_CUSTOM,
    ):
        mode = RULE_MODE_CUSTOM

    default_config = (
        build_business_hours_rule_config(
            legacy_true_tag_ids,
            legacy_false_tag_ids,
        )
        if mode == RULE_MODE_BUSINESS_HOURS
        else build_default_custom_rule_config(
            legacy_true_tag_ids,
            legacy_false_tag_ids,
        )
    )

    trigger_conditions = parsed_config.get(
        "trigger_conditions"
    )
    branch_conditions = parsed_config.get(
        "branch_conditions"
    )

    if not isinstance(
        trigger_conditions,
        list,
    ) or not trigger_conditions:
        trigger_conditions = default_config[
            "trigger_conditions"
        ]

    if not isinstance(
        branch_conditions,
        list,
    ):
        branch_conditions = default_config[
            "branch_conditions"
        ]

    return {
        "version": 1,
        "mode": mode,
        "event": normalize_rule_text(
            parsed_config.get("event"),
            legacy_event_name,
        ),
        "trigger_conditions": [
            normalize_rule_condition(
                condition,
                index=index,
            )
            for index, condition in enumerate(
                trigger_conditions
            )
        ],
        "branch_conditions": [
            normalize_rule_condition(
                condition,
                index=index,
            )
            for index, condition in enumerate(
                branch_conditions
            )
        ],
        "match_tag_ids": normalize_rule_tag_ids(
            parsed_config.get(
                "match_tag_ids",
                default_config[
                    "match_tag_ids"
                ],
            )
        ),
        "else_tag_ids": normalize_rule_tag_ids(
            parsed_config.get(
                "else_tag_ids",
                default_config[
                    "else_tag_ids"
                ],
            )
        ),
    }


def serialize_rule_config(
    config,
    legacy_rule=None,
):

    return json.dumps(
        normalize_rule_config(
            config,
            legacy_rule=legacy_rule,
        ),
        separators=(",", ":"),
    )


def get_rule_primary_tag_id(tag_ids):

    normalized_tag_ids = normalize_rule_tag_ids(
        tag_ids
    )

    if not normalized_tag_ids:
        return None

    return normalized_tag_ids[0]


def build_rule_storage_payload(
    config,
    legacy_rule=None,
):

    normalized_config = normalize_rule_config(
        config,
        legacy_rule=legacy_rule,
    )
    primary_condition = (
        normalized_config[
            "trigger_conditions"
        ][0]
        if normalized_config[
            "trigger_conditions"
        ]
        else {
            "field": "created_at",
            "operator": "during_business_hours",
        }
    )

    return {
        "builder_mode": normalized_config[
            "mode"
        ],
        "config_json": serialize_rule_config(
            normalized_config,
            legacy_rule=legacy_rule,
        ),
        "condition_field": normalize_rule_text(
            primary_condition.get("field"),
            "created_at",
        ),
        "condition_operator": normalize_rule_text(
            primary_condition.get(
                "operator"
            ),
            "during_business_hours",
        ),
        "event_name": normalize_rule_text(
            normalized_config.get("event"),
            "ticket_created",
        ),
        "false_tag_id": get_rule_primary_tag_id(
            normalized_config[
                "else_tag_ids"
            ]
        ),
        "true_tag_id": get_rule_primary_tag_id(
            normalized_config[
                "match_tag_ids"
            ]
        ),
    }


def hydrate_workflow_rule(rule):

    normalized_rule = row_to_dict(rule)

    if normalized_rule is None:
        return None

    normalized_config = normalize_rule_config(
        normalized_rule.get("config_json"),
        legacy_rule=normalized_rule,
    )

    normalized_rule[
        "builder_mode"
    ] = normalized_config["mode"]
    normalized_rule["config"] = normalized_config
    normalized_rule[
        "match_tag_ids"
    ] = normalized_config["match_tag_ids"]
    normalized_rule[
        "else_tag_ids"
    ] = normalized_config["else_tag_ids"]

    return normalized_rule


def get_tag_id_by_name(
    conn,
    tag_name,
):

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id
        FROM tags
        WHERE name = ?
        """,
        (tag_name,)
    )

    row = cursor.fetchone()

    return int(row["id"]) if row else None


def load_profile_ranges(
    conn,
    profile_id,
):

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id,
               day_name,
               start_time,
               end_time,
               sort_order
        FROM business_hour_ranges
        WHERE profile_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (profile_id,)
    )

    return [
        {
            "id": int(row["id"]),
            "day_name": row["day_name"],
            "start_time": normalize_time_string(
                row["start_time"]
            ),
            "end_time": normalize_time_string(
                row["end_time"]
            ),
            "sort_order": int(
                row["sort_order"]
            ),
        }
        for row in cursor.fetchall()
    ]


def upsert_tag_seed(
    conn,
    name,
    description,
    color,
):

    cursor = conn.cursor()
    timestamp = get_timestamp()
    normalized_name = str(name).strip()
    normalized_slug = slugify_tag_name(
        normalized_name
    )

    cursor.execute(
        """
        SELECT id
        FROM tags
        WHERE slug = ?
        """,
        (normalized_slug,)
    )

    row = cursor.fetchone()

    if row:
        cursor.execute(
            """
            UPDATE tags
            SET name = ?,
                description = COALESCE(NULLIF(description, ''), ?),
                color = COALESCE(NULLIF(color, ''), ?),
                updated_at = ?
            WHERE id = ?
            """,
            (
                normalized_name,
                description,
                normalize_color(color),
                timestamp,
                int(row["id"]),
            )
        )
        return int(row["id"])

    cursor.execute(
        """
        INSERT INTO tags (
            name,
            slug,
            description,
            color,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_name,
            normalized_slug,
            description,
            normalize_color(color),
            timestamp,
            timestamp,
        )
    )

    return int(cursor.lastrowid)


def remove_legacy_default_tags(conn):

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id
        FROM tags
        WHERE slug IN (?, ?, ?, ?)
        """,
        tuple(
            sorted(LEGACY_DEFAULT_TAG_SLUGS)
        )
    )

    tag_ids = [
        int(row["id"])
        for row in cursor.fetchall()
    ]

    if not tag_ids:
        return

    timestamp = get_timestamp()

    for tag_id in tag_ids:
        cursor.execute(
            """
            UPDATE workflow_rules
            SET true_tag_id = CASE
                    WHEN true_tag_id = ? THEN NULL
                    ELSE true_tag_id
                END,
                false_tag_id = CASE
                    WHEN false_tag_id = ? THEN NULL
                    ELSE false_tag_id
                END,
                updated_at = ?
            """,
            (
                tag_id,
                tag_id,
                timestamp,
            )
        )

        cursor.execute(
            """
            DELETE FROM ticket_tag_links
            WHERE tag_id = ?
            """,
            (tag_id,)
        )

        cursor.execute(
            """
            DELETE FROM tags
            WHERE id = ?
            """,
            (tag_id,)
        )


def ensure_default_tags(conn):

    remove_legacy_default_tags(conn)

    for tag in DEFAULT_TAGS:
        upsert_tag_seed(
            conn,
            tag["name"],
            tag["description"],
            tag["color"],
        )


def ensure_default_business_hours_profile(conn):

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id
        FROM business_hours_profiles
        WHERE is_default = 1
        ORDER BY id ASC
        LIMIT 1
        """
    )

    row = cursor.fetchone()

    if row:
        profile_id = int(row["id"])
        cursor.execute(
            """
            SELECT COUNT(1)
            FROM business_hour_ranges
            WHERE profile_id = ?
            """,
            (profile_id,)
        )

        range_count = int(
            cursor.fetchone()[0]
        )

        if range_count == 0:
            save_business_hour_ranges(
                conn,
                profile_id,
                build_default_ranges(),
            )

        return profile_id

    timestamp = get_timestamp()
    cursor.execute(
        """
        INSERT INTO business_hours_profiles (
            name,
            timezone,
            description,
            is_default,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, 1, 1, ?, ?)
        """,
        (
            "Default Business Hours",
            DEFAULT_TIMEZONE,
            "Default schedule used by workflow rules.",
            timestamp,
            timestamp,
        )
    )

    profile_id = int(cursor.lastrowid)

    save_business_hour_ranges(
        conn,
        profile_id,
        build_default_ranges(),
    )

    return profile_id


def save_business_hour_ranges(
    conn,
    profile_id,
    ranges,
):

    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM business_hour_ranges
        WHERE profile_id = ?
        """,
        (profile_id,)
    )

    for sort_order, range_item in enumerate(
        sort_ranges(ranges)
    ):
        cursor.execute(
            """
            INSERT INTO business_hour_ranges (
                profile_id,
                day_name,
                start_time,
                end_time,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                range_item["day_name"],
                range_item["start_time"],
                range_item["end_time"],
                sort_order,
            )
        )


def sync_business_hours_rule_windows_with_connection(
    conn
):

    cursor = conn.cursor()
    timestamp = get_timestamp()

    cursor.execute(
        """
        DELETE FROM business_hours_rule_windows
        """
    )

    cursor.execute(
        """
        SELECT id,
               name,
               timezone,
               description,
               is_default,
               is_active,
               created_at,
               updated_at
        FROM business_hours_profiles
        WHERE is_default = 1
        ORDER BY id ASC
        LIMIT 1
        """
    )

    profile = cursor.fetchone()

    if profile is None:
        return

    ranges = load_profile_ranges(
        conn,
        int(profile["id"]),
    )

    if not ranges:
        return

    cursor.execute(
        """
        SELECT workflow_rules.id,
               workflow_rules.rule_key,
               workflow_rules.name,
               workflow_rules.description,
               workflow_rules.event_name,
               workflow_rules.condition_field,
               workflow_rules.condition_operator,
               workflow_rules.builder_mode,
               workflow_rules.true_tag_id,
               workflow_rules.false_tag_id,
               workflow_rules.is_enabled,
               workflow_rules.created_at,
               workflow_rules.updated_at,
               true_tag.name AS true_tag_name,
               false_tag.name AS false_tag_name
        FROM workflow_rules
        LEFT JOIN tags AS true_tag
            ON true_tag.id = workflow_rules.true_tag_id
        LEFT JOIN tags AS false_tag
            ON false_tag.id = workflow_rules.false_tag_id
        WHERE workflow_rules.builder_mode = 'business_hours'
           OR workflow_rules.condition_operator = 'during_business_hours'
        ORDER BY workflow_rules.created_at ASC,
                 workflow_rules.id ASC
        """
    )

    rules = cursor.fetchall()

    for rule in rules:
        for sort_order, range_item in enumerate(
            ranges
        ):
            cursor.execute(
                """
                INSERT INTO business_hours_rule_windows (
                    workflow_rule_id,
                    profile_id,
                    rule_key,
                    rule_name,
                    rule_description,
                    event_name,
                    condition_field,
                    condition_operator,
                    timezone,
                    day_name,
                    start_time,
                    end_time,
                    sort_order,
                    during_tag_id,
                    during_tag_name,
                    after_tag_id,
                    after_tag_name,
                    is_enabled,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(rule["id"]),
                    int(profile["id"]),
                    rule["rule_key"],
                    rule["name"],
                    rule["description"],
                    rule["event_name"],
                    rule["condition_field"],
                    rule["condition_operator"],
                    profile["timezone"],
                    range_item["day_name"],
                    normalize_time_string(
                        range_item["start_time"]
                    ),
                    normalize_time_string(
                        range_item["end_time"]
                    ),
                    sort_order,
                    rule["true_tag_id"],
                    rule["true_tag_name"],
                    rule["false_tag_id"],
                    rule["false_tag_name"],
                    int(rule["is_enabled"] or 0),
                    rule["created_at"]
                    or timestamp,
                    timestamp,
                )
            )


def ensure_default_business_hours_rule(conn):

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id
        FROM workflow_rules
        WHERE rule_key = ?
        """,
        (DEFAULT_RULE_KEY,)
    )

    row = cursor.fetchone()
    timestamp = get_timestamp()
    true_tag_id = get_tag_id_by_name(
        conn,
        "during-business-hours",
    )
    false_tag_id = get_tag_id_by_name(
        conn,
        "outside-business-hours",
    )
    default_config = build_business_hours_rule_config(
        [true_tag_id] if true_tag_id else [],
        [false_tag_id] if false_tag_id else [],
    )
    storage_payload = build_rule_storage_payload(
        default_config
    )

    if row:
        cursor.execute(
            """
            UPDATE workflow_rules
            SET true_tag_id = COALESCE(true_tag_id, ?),
                false_tag_id = COALESCE(false_tag_id, ?),
                builder_mode = COALESCE(builder_mode, ?),
                config_json = CASE
                    WHEN COALESCE(TRIM(config_json), '') = '' THEN ?
                    ELSE config_json
                END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                true_tag_id,
                false_tag_id,
                RULE_MODE_BUSINESS_HOURS,
                storage_payload["config_json"],
                timestamp,
                int(row["id"]),
            )
        )
        return int(row["id"])

    cursor.execute(
        """
        INSERT INTO workflow_rules (
            rule_key,
            name,
            description,
            event_name,
            condition_field,
            condition_operator,
            true_tag_id,
            false_tag_id,
            builder_mode,
            config_json,
            is_enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            DEFAULT_RULE_KEY,
            "Tag tickets by business hours",
            (
                "Tags tickets created during and outside business "
                "hours to track support performance and coverage."
            ),
            "ticket_created",
            "created_at",
            "during_business_hours",
            true_tag_id,
            false_tag_id,
            storage_payload["builder_mode"],
            storage_payload["config_json"],
            timestamp,
            timestamp,
        )
    )

    return int(cursor.lastrowid)


# -----------------------------------
# INITIALIZATION
# -----------------------------------

def initialize_admin_settings():

    global ADMIN_SETTINGS_INITIALIZING
    global ADMIN_SETTINGS_READY

    if ADMIN_SETTINGS_READY:
        return

    if ADMIN_SETTINGS_INITIALIZING:
        return

    ADMIN_SETTINGS_INITIALIZING = True

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                color TEXT DEFAULT '#38bdf8',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_tag_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                tag_id INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                rule_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(ticket_id, tag_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS business_hours_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                timezone TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_default INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS business_hour_ranges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                day_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                event_name TEXT NOT NULL,
                condition_field TEXT NOT NULL,
                condition_operator TEXT NOT NULL,
                true_tag_id INTEGER,
                false_tag_id INTEGER,
                is_enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_column(
            cursor,
            "workflow_rules",
            "builder_mode",
            "TEXT DEFAULT 'business_hours'",
        )
        ensure_column(
            cursor,
            "workflow_rules",
            "config_json",
            "TEXT DEFAULT ''",
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS business_hours_rule_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_rule_id INTEGER NOT NULL,
                profile_id INTEGER NOT NULL,
                rule_key TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                rule_description TEXT DEFAULT '',
                event_name TEXT NOT NULL,
                condition_field TEXT NOT NULL,
                condition_operator TEXT NOT NULL,
                timezone TEXT NOT NULL,
                day_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                during_tag_id INTEGER,
                during_tag_name TEXT,
                after_tag_id INTEGER,
                after_tag_name TEXT,
                is_enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(
                    workflow_rule_id,
                    profile_id,
                    day_name,
                    start_time,
                    end_time
                )
            )
            """
        )

        ensure_default_tags(conn)
        ensure_default_business_hours_profile(
            conn
        )
        ensure_default_business_hours_rule(
            conn
        )
        sync_business_hours_rule_windows_with_connection(
            conn
        )

        conn.commit()
        conn.close()

        ADMIN_SETTINGS_READY = True
        refresh_ticket_business_hours_labels()
        sync_workflow_rule_tags()

    finally:
        ADMIN_SETTINGS_INITIALIZING = False


# -----------------------------------
# TAGS
# -----------------------------------

def get_tags(search_term=""):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    normalized_search = str(
        search_term or ""
    ).strip().lower()

    query = """
        SELECT tags.id,
               tags.name,
               tags.slug,
               tags.description,
               tags.color,
               tags.created_at,
               tags.updated_at,
               COUNT(ticket_tag_links.ticket_id) AS ticket_count
        FROM tags
        LEFT JOIN ticket_tag_links
            ON ticket_tag_links.tag_id = tags.id
    """

    parameters = []

    if normalized_search:
        query += """
        WHERE LOWER(tags.name) LIKE ?
           OR LOWER(COALESCE(tags.description, '')) LIKE ?
        """
        parameters.extend(
            [
                f"%{normalized_search}%",
                f"%{normalized_search}%",
            ]
        )

    query += """
        GROUP BY tags.id
        ORDER BY ticket_count DESC,
                 tags.name ASC
    """

    cursor.execute(
        query,
        tuple(parameters),
    )

    tags = [
        {
            **row_to_dict(row),
            "ticket_count": int(
                row["ticket_count"] or 0
            ),
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    return tags


def get_tag(tag_id):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM tags
        WHERE id = ?
        """,
        (tag_id,)
    )

    tag = row_to_dict(
        cursor.fetchone()
    )

    conn.close()

    return tag


def create_tag(
    name,
    description="",
    color="",
):

    initialize_admin_settings()

    normalized_name = str(
        name or ""
    ).strip()

    if not normalized_name:
        raise ValueError(
            "Tag name is required."
        )

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    normalized_color = normalize_color(
        color,
        fallback_color=TAG_COLOR_PALETTE[
            len(get_tags()) % len(
                TAG_COLOR_PALETTE
            )
        ],
    )
    base_slug = slugify_tag_name(
        normalized_name
    )
    unique_slug = base_slug
    suffix = 2

    while True:
        cursor.execute(
            """
            SELECT id
            FROM tags
            WHERE slug = ?
            """,
            (unique_slug,)
        )

        if cursor.fetchone() is None:
            break

        unique_slug = (
            f"{base_slug}-{suffix}"
        )
        suffix += 1

    cursor.execute(
        """
        INSERT INTO tags (
            name,
            slug,
            description,
            color,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_name,
            unique_slug,
            str(description or "").strip(),
            normalized_color,
            timestamp,
            timestamp,
        )
    )

    tag_id = int(cursor.lastrowid)

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()

    return tag_id


def update_tag(
    tag_id,
    name,
    description="",
    color="",
):

    initialize_admin_settings()

    normalized_name = str(
        name or ""
    ).strip()

    if not normalized_name:
        raise ValueError(
            "Tag name is required."
        )

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    tag = get_tag(tag_id)

    if tag is None:
        conn.close()
        raise ValueError(
            "Tag not found."
        )

    base_slug = slugify_tag_name(
        normalized_name
    )
    unique_slug = base_slug
    suffix = 2

    while True:
        cursor.execute(
            """
            SELECT id
            FROM tags
            WHERE slug = ?
              AND id != ?
            """,
            (
                unique_slug,
                tag_id,
            )
        )

        if cursor.fetchone() is None:
            break

        unique_slug = (
            f"{base_slug}-{suffix}"
        )
        suffix += 1

    cursor.execute(
        """
        UPDATE tags
        SET name = ?,
            slug = ?,
            description = ?,
            color = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            normalized_name,
            unique_slug,
            str(description or "").strip(),
            normalize_color(
                color,
                fallback_color=tag.get(
                    "color",
                    "#38bdf8",
                ),
            ),
            timestamp,
            tag_id,
        )
    )

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()


def delete_tag(tag_id):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE workflow_rules
        SET true_tag_id = CASE
                WHEN true_tag_id = ? THEN NULL
                ELSE true_tag_id
            END,
            false_tag_id = CASE
                WHEN false_tag_id = ? THEN NULL
                ELSE false_tag_id
            END,
            updated_at = ?
        """,
        (
            tag_id,
            tag_id,
            get_timestamp(),
        )
    )

    cursor.execute(
        """
        DELETE FROM ticket_tag_links
        WHERE tag_id = ?
        """,
        (tag_id,)
    )

    cursor.execute(
        """
        DELETE FROM tags
        WHERE id = ?
        """,
        (tag_id,)
    )

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()


def merge_tags(
    target_tag_id,
    source_tag_ids,
):

    initialize_admin_settings()

    source_tag_ids = [
        int(tag_id)
        for tag_id in source_tag_ids
        if int(tag_id) != int(target_tag_id)
    ]

    if not source_tag_ids:
        return

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()

    for source_tag_id in source_tag_ids:
        cursor.execute(
            """
            SELECT ticket_id,
                   source,
                   rule_id
            FROM ticket_tag_links
            WHERE tag_id = ?
            """,
            (source_tag_id,)
        )

        for row in cursor.fetchall():
            cursor.execute(
                """
                INSERT OR IGNORE INTO ticket_tag_links (
                    ticket_id,
                    tag_id,
                    source,
                    rule_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["ticket_id"],
                    target_tag_id,
                    row["source"],
                    row["rule_id"],
                    timestamp,
                )
            )

        cursor.execute(
            """
            UPDATE workflow_rules
            SET true_tag_id = CASE
                    WHEN true_tag_id = ? THEN ?
                    ELSE true_tag_id
                END,
                false_tag_id = CASE
                    WHEN false_tag_id = ? THEN ?
                    ELSE false_tag_id
                END,
                updated_at = ?
            """,
            (
                source_tag_id,
                target_tag_id,
                source_tag_id,
                target_tag_id,
                timestamp,
            )
        )

        cursor.execute(
            """
            DELETE FROM ticket_tag_links
            WHERE tag_id = ?
            """,
            (source_tag_id,)
        )

        cursor.execute(
            """
            DELETE FROM tags
            WHERE id = ?
            """,
            (source_tag_id,)
        )

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()


def get_ticket_tags(ticket_id):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT tags.id,
               tags.name,
               tags.slug,
               tags.description,
               tags.color,
               ticket_tag_links.source,
               ticket_tag_links.rule_id
        FROM ticket_tag_links
        INNER JOIN tags
            ON tags.id = ticket_tag_links.tag_id
        WHERE ticket_tag_links.ticket_id = ?
        ORDER BY tags.name ASC
        """,
        (ticket_id,)
    )

    tags = [
        row_to_dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return tags


def set_ticket_tags(
    ticket_id,
    tag_ids,
):

    initialize_admin_settings()

    normalized_tag_ids = {
        int(tag_id)
        for tag_id in tag_ids
    }

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT tag_id
        FROM ticket_tag_links
        WHERE ticket_id = ?
          AND source = 'manual'
        """,
        (ticket_id,)
    )

    existing_manual_ids = {
        int(row["tag_id"])
        for row in cursor.fetchall()
    }

    remove_ids = (
        existing_manual_ids
        - normalized_tag_ids
    )
    add_ids = (
        normalized_tag_ids
        - existing_manual_ids
    )

    for tag_id in remove_ids:
        cursor.execute(
            """
            DELETE FROM ticket_tag_links
            WHERE ticket_id = ?
              AND tag_id = ?
              AND source = 'manual'
            """,
            (
                ticket_id,
                tag_id,
            )
        )

    timestamp = get_timestamp()

    for tag_id in add_ids:
        cursor.execute(
            """
            INSERT OR IGNORE INTO ticket_tag_links (
                ticket_id,
                tag_id,
                source,
                rule_id,
                created_at
            )
            VALUES (?, ?, 'manual', NULL, ?)
            """,
            (
                ticket_id,
                tag_id,
                timestamp,
            )
        )

    conn.commit()
    conn.close()


def remove_ticket_tag_links(ticket_id):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM ticket_tag_links
        WHERE ticket_id = ?
        """,
        (ticket_id,)
    )

    conn.commit()
    conn.close()


# -----------------------------------
# BUSINESS HOURS
# -----------------------------------

def get_business_hours_profiles():

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM business_hours_profiles
        ORDER BY is_default DESC,
                 name ASC
        """
    )

    profiles = []

    for row in cursor.fetchall():
        profile = row_to_dict(row)
        profile["ranges"] = load_profile_ranges(
            conn,
            profile["id"],
        )
        profile["summary"] = build_schedule_summary(
            profile["ranges"]
        )
        profiles.append(profile)

    conn.close()

    return profiles


def get_business_hours_profile(profile_id=None):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()

    if profile_id is None:
        cursor.execute(
            """
            SELECT *
            FROM business_hours_profiles
            WHERE is_default = 1
            ORDER BY id ASC
            LIMIT 1
            """
        )
    else:
        cursor.execute(
            """
            SELECT *
            FROM business_hours_profiles
            WHERE id = ?
            """,
            (profile_id,)
        )

    row = cursor.fetchone()

    if row is None:
        conn.close()
        return None

    profile = row_to_dict(row)
    profile["ranges"] = load_profile_ranges(
        conn,
        profile["id"],
    )
    profile["summary"] = build_schedule_summary(
        profile["ranges"]
    )

    conn.close()

    return profile


def create_business_hours_profile(
    name,
    timezone_name,
    ranges,
    description="",
    is_default=False,
):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()

    if is_default:
        cursor.execute(
            """
            UPDATE business_hours_profiles
            SET is_default = 0,
                updated_at = ?
            WHERE is_default = 1
            """,
            (timestamp,)
        )

    cursor.execute(
        """
        INSERT INTO business_hours_profiles (
            name,
            timezone,
            description,
            is_default,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (
            str(name or "").strip()
            or "Custom Business Hours",
            str(timezone_name or "").strip()
            or DEFAULT_TIMEZONE,
            str(description or "").strip(),
            1 if is_default else 0,
            timestamp,
            timestamp,
        )
    )

    profile_id = int(cursor.lastrowid)
    save_business_hour_ranges(
        conn,
        profile_id,
        ranges,
    )

    conn.commit()
    conn.close()

    if is_default:
        sync_business_hours_rule_windows()
        refresh_ticket_business_hours_labels()
        sync_workflow_rule_tags()

    return profile_id


def update_business_hours_profile(
    profile_id,
    name,
    timezone_name,
    ranges,
    description="",
):

    initialize_admin_settings()

    profile = get_business_hours_profile(
        profile_id
    )

    if profile is None:
        raise ValueError(
            "Business hours profile not found."
        )

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    cursor.execute(
        """
        UPDATE business_hours_profiles
        SET name = ?,
            timezone = ?,
            description = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(name or "").strip()
            or profile.get("name")
            or "Business Hours",
            str(timezone_name or "").strip()
            or DEFAULT_TIMEZONE,
            str(description or "").strip(),
            timestamp,
            profile_id,
        )
    )

    save_business_hour_ranges(
        conn,
        profile_id,
        ranges,
    )

    conn.commit()
    conn.close()

    if int(profile.get("is_default", 0)) == 1:
        sync_business_hours_rule_windows()
        refresh_ticket_business_hours_labels()
        sync_workflow_rule_tags()


def delete_business_hours_profile(profile_id):

    initialize_admin_settings()

    profile = get_business_hours_profile(
        profile_id
    )

    if profile is None:
        return

    if int(profile.get("is_default", 0)) == 1:
        raise ValueError(
            "Default business hours cannot be deleted."
        )

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM business_hour_ranges
        WHERE profile_id = ?
        """,
        (profile_id,)
    )
    cursor.execute(
        """
        DELETE FROM business_hours_profiles
        WHERE id = ?
        """,
        (profile_id,)
    )

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()


def sync_business_hours_rule_windows():

    initialize_admin_settings()

    conn = get_connection()
    sync_business_hours_rule_windows_with_connection(
        conn
    )
    conn.commit()
    conn.close()


def get_business_hours_rule_windows():

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM business_hours_rule_windows
        ORDER BY workflow_rule_id ASC,
                 sort_order ASC,
                 day_name ASC,
                 start_time ASC
        """
    )

    rows = [
        row_to_dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return rows


def is_within_business_hours(
    reference_time=None,
    profile=None,
):

    if profile is None:
        profile = get_business_hours_profile()

    if profile is None:
        return False

    localized_reference_time = parse_reference_datetime(
        reference_time,
        timezone_name=profile.get(
            "timezone",
            DEFAULT_TIMEZONE,
        ),
    )

    weekday_name = DAY_NAMES[
        localized_reference_time.weekday()
    ]

    day_ranges = [
        range_item
        for range_item in profile.get(
            "ranges",
            [],
        )
        if range_item.get("day_name")
        == weekday_name
    ]

    if not day_ranges:
        return False

    current_time = localized_reference_time.time()

    for range_item in day_ranges:
        start_time = parse_time_string(
            range_item.get("start_time")
        )
        end_time = parse_time_string(
            range_item.get("end_time")
        )

        if start_time <= current_time < end_time:
            return True

    return False


def get_business_hours_label(reference_time=None):

    profile = get_business_hours_profile()

    if profile is None:
        return "Business Hours"

    localized_reference_time = parse_reference_datetime(
        reference_time,
        timezone_name=profile.get(
            "timezone",
            DEFAULT_TIMEZONE,
        ),
    )

    if is_within_business_hours(
        localized_reference_time,
        profile=profile,
    ):
        return "Business Hours"

    if localized_reference_time.weekday() >= 5:
        return "Weekend Coverage"

    return "After Hours"


def refresh_ticket_business_hours_labels():

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT ticket_id,
                   created_at
            FROM tickets
            """
        )
    except sqlite3.OperationalError:
        conn.close()
        return

    rows = cursor.fetchall()

    for row in rows:
        cursor.execute(
            """
            UPDATE tickets
            SET business_hours_tag = ?
            WHERE ticket_id = ?
            """,
            (
                get_business_hours_label(
                    row["created_at"]
                ),
                row["ticket_id"],
            )
        )

    conn.commit()
    conn.close()


# -----------------------------------
# WORKFLOW RULES
# -----------------------------------

def get_workflow_rules():

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT workflow_rules.*,
               true_tag.name AS true_tag_name,
               true_tag.color AS true_tag_color,
               false_tag.name AS false_tag_name,
               false_tag.color AS false_tag_color
        FROM workflow_rules
        LEFT JOIN tags AS true_tag
            ON true_tag.id = workflow_rules.true_tag_id
        LEFT JOIN tags AS false_tag
            ON false_tag.id = workflow_rules.false_tag_id
        ORDER BY workflow_rules.created_at ASC,
                 workflow_rules.id ASC
        """
    )

    rules = [
        hydrate_workflow_rule(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return rules


def get_workflow_rule(rule_id=None):

    rules = get_workflow_rules()

    if not rules:
        return None

    if rule_id is None:
        return rules[0]

    for rule in rules:
        if int(rule["id"]) == int(rule_id):
            return rule

    return None


def update_workflow_rule(
    rule_id,
    name,
    description,
    true_tag_id,
    false_tag_id,
    is_enabled,
    builder_mode=None,
    config=None,
):

    initialize_admin_settings()

    existing_rule = get_workflow_rule(
        rule_id
    )

    if existing_rule is None:
        raise ValueError(
            "Workflow rule not found."
        )

    merged_config = normalize_rule_config(
        config,
        legacy_rule={
            **existing_rule,
            "builder_mode": builder_mode
            or existing_rule.get(
                "builder_mode"
            ),
            "true_tag_id": true_tag_id
            if true_tag_id is not None
            else existing_rule.get(
                "true_tag_id"
            ),
            "false_tag_id": false_tag_id
            if false_tag_id is not None
            else existing_rule.get(
                "false_tag_id"
            ),
        },
    )

    if true_tag_id is not None:
        merged_config[
            "match_tag_ids"
        ] = normalize_rule_tag_ids(
            [
                true_tag_id,
                *merged_config[
                    "match_tag_ids"
                ],
            ]
        )

    if false_tag_id is not None:
        merged_config[
            "else_tag_ids"
        ] = normalize_rule_tag_ids(
            [
                false_tag_id,
                *merged_config[
                    "else_tag_ids"
                ],
            ]
        )

    storage_payload = build_rule_storage_payload(
        {
            **merged_config,
            "mode": builder_mode
            or merged_config.get("mode")
            or existing_rule.get(
                "builder_mode"
            )
            or RULE_MODE_CUSTOM,
        },
        legacy_rule=existing_rule,
    )

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE workflow_rules
        SET name = ?,
            description = ?,
            event_name = ?,
            condition_field = ?,
            condition_operator = ?,
            true_tag_id = ?,
            false_tag_id = ?,
            builder_mode = ?,
            config_json = ?,
            is_enabled = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(name or "").strip()
            or "Workflow Rule",
            str(description or "").strip(),
            storage_payload["event_name"],
            storage_payload[
                "condition_field"
            ],
            storage_payload[
                "condition_operator"
            ],
            storage_payload["true_tag_id"],
            storage_payload["false_tag_id"],
            storage_payload[
                "builder_mode"
            ],
            storage_payload["config_json"],
            1 if is_enabled else 0,
            get_timestamp(),
            rule_id,
        )
    )

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()
    sync_workflow_rule_tags(rule_id)


def create_workflow_rule():

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    true_tag_id = get_tag_id_by_name(
        conn,
        "vip",
    )
    false_tag_id = get_tag_id_by_name(
        conn,
        "outside-business-hours",
    )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM workflow_rules
        """
    )

    next_rule_number = int(
        cursor.fetchone()[0] or 0
    ) + 1
    rule_name = (
        f"[Auto Tag] Workflow Rule {next_rule_number}"
    )
    base_rule_key = slugify_tag_name(
        rule_name
    )
    rule_key = base_rule_key
    suffix = 2

    while True:
        cursor.execute(
            """
            SELECT id
            FROM workflow_rules
            WHERE rule_key = ?
            """,
            (rule_key,)
        )

        if cursor.fetchone() is None:
            break

        rule_key = (
            f"{base_rule_key}-{suffix}"
        )
        suffix += 1

    default_config = build_default_custom_rule_config(
        [true_tag_id] if true_tag_id else [],
        [],
    )
    storage_payload = build_rule_storage_payload(
        default_config
    )

    cursor.execute(
        """
        INSERT INTO workflow_rules (
            rule_key,
            name,
            description,
            event_name,
            condition_field,
            condition_operator,
            true_tag_id,
            false_tag_id,
            builder_mode,
            config_json,
            is_enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            rule_key,
            rule_name,
            "Create a custom automation rule with Gorgias-style conditions and light tag actions.",
            storage_payload["event_name"],
            storage_payload[
                "condition_field"
            ],
            storage_payload[
                "condition_operator"
            ],
            storage_payload["true_tag_id"],
            storage_payload["false_tag_id"],
            storage_payload[
                "builder_mode"
            ],
            storage_payload["config_json"],
            timestamp,
            timestamp,
        )
    )

    new_rule_id = int(cursor.lastrowid)

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()
    sync_workflow_rule_tags(new_rule_id)

    return new_rule_id


def duplicate_workflow_rule(rule_id):

    initialize_admin_settings()

    rule = get_workflow_rule(rule_id)

    if rule is None:
        raise ValueError(
            "Workflow rule not found."
        )

    conn = get_connection()
    cursor = conn.cursor()
    timestamp = get_timestamp()
    base_rule_key = slugify_tag_name(
        rule.get("name")
    )
    copy_index = 2
    duplicate_rule_key = (
        f"{base_rule_key}_copy"
    )

    while True:
        cursor.execute(
            """
            SELECT id
            FROM workflow_rules
            WHERE rule_key = ?
            """,
            (duplicate_rule_key,)
        )

        if cursor.fetchone() is None:
            break

        duplicate_rule_key = (
            f"{base_rule_key}_copy_{copy_index}"
        )
        copy_index += 1

    storage_payload = build_rule_storage_payload(
        rule.get("config"),
        legacy_rule=rule,
    )

    cursor.execute(
        """
        INSERT INTO workflow_rules (
            rule_key,
            name,
            description,
            event_name,
            condition_field,
            condition_operator,
            true_tag_id,
            false_tag_id,
            builder_mode,
            config_json,
            is_enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            duplicate_rule_key,
            f"{rule['name']} Copy",
            rule.get("description", ""),
            storage_payload["event_name"],
            storage_payload[
                "condition_field"
            ],
            storage_payload[
                "condition_operator"
            ],
            storage_payload["true_tag_id"],
            storage_payload["false_tag_id"],
            storage_payload[
                "builder_mode"
            ],
            storage_payload["config_json"],
            timestamp,
            timestamp,
        )
    )

    new_rule_id = int(cursor.lastrowid)

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()

    return new_rule_id


def delete_workflow_rule(rule_id):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM ticket_tag_links
        WHERE source = 'rule'
          AND rule_id = ?
        """,
        (rule_id,)
    )
    cursor.execute(
        """
        DELETE FROM workflow_rules
        WHERE id = ?
        """,
        (rule_id,)
    )

    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()


def restore_default_workflow_rule():

    initialize_admin_settings()

    conn = get_connection()
    rule_id = ensure_default_business_hours_rule(
        conn
    )
    conn.commit()
    conn.close()

    sync_business_hours_rule_windows()
    sync_workflow_rule_tags(rule_id)

    return rule_id


def normalize_rule_boolean(value):

    if isinstance(value, bool):
        return value

    return str(value or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def resolve_customer_rule_profile(
    email,
    customer_cache=None,
):

    normalized_email = normalize_rule_text(
        email,
        "",
    ).lower()

    if not normalized_email:
        return {
            "is_vip": False,
            "order_count": 0,
            "total_spent": 0.0,
        }

    if customer_cache is None:
        customer_cache = {}

    if normalized_email in customer_cache:
        return customer_cache[
            normalized_email
        ]

    customer_data = {}

    customer_record = (
        customer_data.get("customer")
        if isinstance(customer_data, dict)
        else {}
    ) or {}
    orders = (
        customer_data.get("orders")
        if isinstance(customer_data, dict)
        else []
    ) or []

    order_count = parse_int_value(
        customer_record.get(
            "total_orders"
        )
        or customer_record.get(
            "orders_count"
        )
        or customer_record.get(
            "report_order_count"
        )
        or len(orders),
        fallback=len(orders),
    )
    total_spent = parse_float_value(
        customer_record.get(
            "total_spent"
        )
        or customer_record.get(
            "total_spend"
        )
        or customer_record.get(
            "report_total_spend"
        )
        or 0,
        fallback=0,
    )

    customer_profile = {
        "is_vip": (
            order_count >= 10
            or total_spent >= 1000
        ),
        "order_count": order_count,
        "total_spent": total_spent,
    }
    customer_cache[
        normalized_email
    ] = customer_profile

    return customer_profile


def build_ticket_rule_context(
    conn,
    ticket,
    profile=None,
    customer_cache=None,
    include_customer_profile=True,
):

    ticket = row_to_dict(ticket)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) AS agent_message_count
        FROM messages
        WHERE ticket_id = ?
          AND LOWER(sender) = 'agent'
        """,
        (ticket["ticket_id"],)
    )

    agent_message_count = parse_int_value(
        cursor.fetchone()[
            "agent_message_count"
        ],
        fallback=0,
    )

    customer_profile = {
        "is_vip": False,
        "order_count": 0,
        "total_spent": 0.0,
    }

    if include_customer_profile:
        customer_profile = resolve_customer_rule_profile(
            ticket.get("customer_email"),
            customer_cache=customer_cache,
        )

    return {
        "assigned_agent": normalize_rule_text(
            ticket.get(
                "assigned_agent"
            ),
            "",
        ),
        "business_hours": is_within_business_hours(
            ticket.get("created_at"),
            profile=profile,
        ),
        "created_at": ticket.get(
            "created_at"
        ),
        "customer_email": normalize_rule_text(
            ticket.get(
                "customer_email"
            ),
            "",
        ),
        "customer_order_count": customer_profile[
            "order_count"
        ],
        "customer_total_spent": customer_profile[
            "total_spent"
        ],
        "customer_vip": customer_profile[
            "is_vip"
        ],
        "issue_type": normalize_rule_text(
            ticket.get("issue_type"),
            "",
        ),
        "message_from_agent": (
            agent_message_count > 0
        ),
        "priority": normalize_rule_text(
            ticket.get("priority"),
            "",
        ),
        "ticket_status": normalize_rule_text(
            ticket.get("status"),
            "",
        ),
    }


def rule_requires_customer_profile(rule):

    config = normalize_rule_config(
        rule.get("config"),
        legacy_rule=rule,
    )

    return any(
        normalize_rule_text(
            condition.get("field"),
            "ticket_status",
        ) in RULE_CUSTOMER_PROFILE_FIELDS
        for condition in (
            config.get("trigger_conditions", [])
            + config.get("branch_conditions", [])
        )
    )


def rules_require_customer_profile(rules):

    return any(
        int(rule.get("is_enabled", 0))
        and rule_requires_customer_profile(rule)
        for rule in rules
    )


def evaluate_rule_condition(
    condition,
    ticket_context,
):

    field_name = normalize_rule_text(
        condition.get("field"),
        "ticket_status",
    )
    operator = normalize_rule_text(
        condition.get("operator"),
        "is",
    )
    expected_value = condition.get(
        "value",
        "",
    )

    if field_name == "created_at":
        if operator == "during_business_hours":
            return bool(
                ticket_context.get(
                    "business_hours"
                )
            )

        if operator == "outside_business_hours":
            return not bool(
                ticket_context.get(
                    "business_hours"
                )
            )

        return False

    actual_value = ticket_context.get(
        field_name
    )

    if field_name in RULE_NUMERIC_FIELDS:
        actual_number = parse_float_value(
            actual_value,
            fallback=0,
        )
        expected_number = parse_float_value(
            expected_value,
            fallback=0,
        )

        if operator == "greater_or_equal":
            return actual_number >= expected_number

        if operator == "greater_than":
            return actual_number > expected_number

        if operator == "less_or_equal":
            return actual_number <= expected_number

        if operator == "less_than":
            return actual_number < expected_number

        if operator == "is_not":
            return actual_number != expected_number

        return actual_number == expected_number

    if field_name in RULE_BOOLEAN_FIELDS:
        actual_boolean = normalize_rule_boolean(
            actual_value
        )
        expected_boolean = normalize_rule_boolean(
            expected_value
        )

        if operator == "is_not":
            return actual_boolean != expected_boolean

        return actual_boolean == expected_boolean

    actual_text = normalize_rule_text(
        actual_value,
        "",
    ).lower()
    expected_text = normalize_rule_text(
        expected_value,
        "",
    ).lower()

    if operator == "contains":
        return expected_text in actual_text

    if operator == "not_contains":
        return expected_text not in actual_text

    if operator == "is_not":
        return actual_text != expected_text

    return actual_text == expected_text


def resolve_rule_tag_ids_for_ticket(
    rule,
    ticket_context,
):

    config = normalize_rule_config(
        rule.get("config"),
        legacy_rule=rule,
    )

    trigger_matches = all(
        evaluate_rule_condition(
            condition,
            ticket_context,
        )
        for condition in config.get(
            "trigger_conditions",
            [],
        )
    )
    branch_conditions = config.get(
        "branch_conditions",
        [],
    )
    branch_matches = (
        all(
            evaluate_rule_condition(
                condition,
                ticket_context,
            )
            for condition in branch_conditions
        )
        if branch_conditions
        else True
    )

    if trigger_matches and branch_matches:
        return normalize_rule_tag_ids(
            config.get(
                "match_tag_ids",
                [],
            )
        )

    return normalize_rule_tag_ids(
        config.get(
            "else_tag_ids",
            [],
        )
    )


def apply_workflow_rules_to_ticket(ticket_id):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ticket_id,
               created_at,
               customer_email,
               issue_type,
               priority,
               status,
               assigned_agent
        FROM tickets
        WHERE ticket_id = ?
        """,
        (ticket_id,)
    )

    ticket = cursor.fetchone()

    if ticket is None:
        conn.close()
        return []

    rules = get_workflow_rules()
    profile = get_business_hours_profile()
    assigned_tag_ids = []
    customer_cache = {}
    needs_customer_profile = (
        rules_require_customer_profile(rules)
    )
    ticket_context = build_ticket_rule_context(
        conn,
        ticket,
        profile=profile,
        customer_cache=customer_cache,
        include_customer_profile=needs_customer_profile,
    )

    for rule in rules:
        cursor.execute(
            """
            DELETE FROM ticket_tag_links
            WHERE ticket_id = ?
              AND source = 'rule'
              AND rule_id = ?
            """,
            (
                ticket_id,
                rule["id"],
            )
        )

        if not int(rule.get("is_enabled", 0)):
            continue

        tag_ids = resolve_rule_tag_ids_for_ticket(
            rule,
            ticket_context,
        )

        if not tag_ids:
            continue

        for tag_id in tag_ids:
            cursor.execute(
                """
                INSERT OR IGNORE INTO ticket_tag_links (
                    ticket_id,
                    tag_id,
                    source,
                    rule_id,
                    created_at
                )
                VALUES (?, ?, 'rule', ?, ?)
                """,
                (
                    ticket_id,
                    tag_id,
                    rule["id"],
                    get_timestamp(),
                )
            )

            assigned_tag_ids.append(
                int(tag_id)
            )

    conn.commit()
    conn.close()

    return assigned_tag_ids


def sync_workflow_rule_tags(rule_id=None):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT ticket_id
            FROM tickets
            ORDER BY created_at ASC,
                     ticket_id ASC
            """
        )
    except sqlite3.OperationalError:
        conn.close()
        return

    ticket_ids = [
        row["ticket_id"]
        for row in cursor.fetchall()
    ]

    conn.close()

    if rule_id is None:
        for ticket_id in ticket_ids:
            apply_workflow_rules_to_ticket(
                ticket_id
            )
        return

    conn = get_connection()
    cursor = conn.cursor()
    profile = get_business_hours_profile()
    rule = get_workflow_rule(rule_id)
    customer_cache = {}

    if rule is None:
        cursor.execute(
            """
            DELETE FROM ticket_tag_links
            WHERE source = 'rule'
              AND rule_id = ?
            """,
            (rule_id,)
        )
        conn.commit()
        conn.close()
        return

    for ticket_id in ticket_ids:
        cursor.execute(
            """
            SELECT ticket_id,
                   created_at,
                   customer_email,
                   issue_type,
                   priority,
                   status,
                   assigned_agent
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,)
        )

        ticket = cursor.fetchone()

        cursor.execute(
            """
            DELETE FROM ticket_tag_links
            WHERE ticket_id = ?
              AND source = 'rule'
              AND rule_id = ?
            """,
            (
                ticket_id,
                rule_id,
            )
        )

        if ticket is None or not int(
            rule.get("is_enabled", 0)
        ):
            continue

        needs_customer_profile = (
            rule_requires_customer_profile(rule)
        )
        ticket_context = build_ticket_rule_context(
            conn,
            ticket,
            profile=profile,
            customer_cache=customer_cache,
            include_customer_profile=needs_customer_profile,
        )
        tag_ids = resolve_rule_tag_ids_for_ticket(
            rule,
            ticket_context,
        )

        if not tag_ids:
            continue

        for tag_id in tag_ids:
            cursor.execute(
                """
                INSERT OR IGNORE INTO ticket_tag_links (
                    ticket_id,
                    tag_id,
                    source,
                    rule_id,
                    created_at
                )
                VALUES (?, ?, 'rule', ?, ?)
                """,
                (
                    ticket_id,
                    tag_id,
                    rule_id,
                    get_timestamp(),
                )
            )

    conn.commit()
    conn.close()


def get_rule_affected_tickets(rule_id):

    initialize_admin_settings()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT tickets.ticket_id,
               tickets.customer_email,
               tickets.issue,
               tickets.status,
               tickets.priority,
               tickets.business_hours_tag,
               tickets.created_at,
               GROUP_CONCAT(tags.name, ', ') AS applied_tag
        FROM tickets
        LEFT JOIN ticket_tag_links
            ON ticket_tag_links.ticket_id = tickets.ticket_id
           AND ticket_tag_links.source = 'rule'
           AND ticket_tag_links.rule_id = ?
        LEFT JOIN tags
            ON tags.id = ticket_tag_links.tag_id
        GROUP BY tickets.ticket_id,
                 tickets.customer_email,
                 tickets.issue,
                 tickets.status,
                 tickets.priority,
                 tickets.business_hours_tag,
                 tickets.created_at
        ORDER BY tickets.created_at DESC,
                 tickets.ticket_id DESC
        """,
        (rule_id,)
    )

    tickets = [
        row_to_dict(row)
        for row in cursor.fetchall()
    ]

    conn.close()

    return tickets
