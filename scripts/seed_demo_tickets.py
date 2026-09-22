"""Replace local tickets with five synthetic AcroBuild examples.

Run from the repository root: python scripts/seed_demo_tickets.py --apply
The SQLite database is intentionally ignored by Git; this script is the
reproducible source for demo ticket data in another checkout.
"""

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.database_service import DB_PATH, delete_attachment_records  # noqa: E402


DEMO_TICKETS = (
    (
        "[DEMO] Please help me schedule a site visit for an AcroBuild project next weekend.",
        "demo.sitevisit@example.com", "Site Visit", "Medium", "Site Visit Request", "Sales Advisory",
    ),
    (
        "[DEMO] I paid a booking amount but have not received a payment receipt.",
        "demo.payment@example.com", "Payments", "High", "Payment Plan", "Project Finance",
    ),
    (
        "[DEMO] Which documents are needed before signing the sale agreement?",
        "demo.documents@example.com", "Documentation", "Low", "Legal Documentation", "Documentation Desk",
    ),
    (
        "[DEMO] Please share the expected handover process and inspection checklist.",
        "demo.handover@example.com", "Handover", "Medium", "Possession / Handover", "Handover and Care",
    ),
    (
        "[DEMO] There is a water leak in my flat after handover; please arrange an inspection.",
        "demo.maintenance@example.com", "Maintenance", "High", "Maintenance Request", "Handover and Care",
    ),
)


def _quoted_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def replace_with_demo_tickets(db_path=DB_PATH):
    """Return the removed count and new IDs; leave other workspace data intact."""
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Initialized SQLite database not found: {db_path}")

    with closing(sqlite3.connect(db_path, timeout=30)) as connection, connection:
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("BEGIN IMMEDIATE")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"tickets", "messages", "ticket_counters"}
        if not required.issubset(tables):
            raise RuntimeError("Initialize the application database before seeding demo tickets.")

        old_count = connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        attachments = [
            row[0] for row in connection.execute("SELECT attachments_json FROM messages")
        ]
        # Include optional ticket-linked tables (feedback, proposals, tags) so
        # old ticket IDs cannot leave orphaned data behind.
        for table in sorted(tables - {"tickets"}):
            columns = {
                row[1] for row in connection.execute(
                    f"PRAGMA table_info({_quoted_identifier(table)})"
                )
            }
            if "ticket_id" in columns:
                connection.execute(f"DELETE FROM {_quoted_identifier(table)}")
        connection.execute("DELETE FROM tickets")
        connection.execute(
            "INSERT INTO ticket_counters(name, next_value) VALUES ('ticket_id', 1) "
            "ON CONFLICT(name) DO UPDATE SET next_value=1"
        )

        ids = []
        now = datetime.now(timezone.utc)
        for index, (issue, email, issue_type, priority, intent, queue) in enumerate(DEMO_TICKETS, 1):
            ticket_id = f"TK{index:06d}"
            timestamp = (now - timedelta(minutes=20 * (len(DEMO_TICKETS) - index))).isoformat(timespec="seconds")
            connection.execute(
                "INSERT INTO tickets (ticket_id, issue, customer_email, issue_type, priority, "
                "status, assigned_agent, unread_count, brand_tag, intent_tag, "
                "business_hours_tag, queue_name, assignment_method, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'Open', '', 1, 'Acrobuild', ?, '', ?, 'Demo Seed', ?, ?)",
                (ticket_id, issue, email, issue_type, priority, intent, queue, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO messages (ticket_id, sender, message, created_at, attachments_json) "
                "VALUES (?, 'customer', ?, ?, '[]')",
                (ticket_id, issue, timestamp),
            )
            ids.append(ticket_id)
        connection.execute(
            "UPDATE ticket_counters SET next_value=? WHERE name='ticket_id'",
            (len(ids) + 1,),
        )

    if db_path.resolve() == Path(DB_PATH).resolve():
        delete_attachment_records(attachments)
    return old_count, ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete existing tickets and create five demo tickets")
    args = parser.parse_args()
    if not args.apply:
        parser.error("Pass --apply to replace existing tickets.")
    removed, ids = replace_with_demo_tickets()
    print(f"Removed {removed} tickets and created {len(ids)} demo tickets: {', '.join(ids)}")


if __name__ == "__main__":
    main()
