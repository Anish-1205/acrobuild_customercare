import sqlite3

import pytest

from scripts.seed_demo_tickets import replace_with_demo_tickets


def test_replaces_ticket_history_and_preserves_other_workspace_data(tmp_path):
    path = tmp_path / "workspace.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE tickets (
                ticket_id TEXT PRIMARY KEY, issue TEXT, customer_email TEXT,
                issue_type TEXT, priority TEXT, status TEXT, assigned_agent TEXT,
                unread_count INTEGER, brand_tag TEXT, intent_tag TEXT,
                business_hours_tag TEXT, queue_name TEXT, assignment_method TEXT,
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE messages (
                ticket_id TEXT, sender TEXT, message TEXT, created_at TEXT,
                attachments_json TEXT
            );
            CREATE TABLE ticket_notes (ticket_id TEXT, note TEXT);
            CREATE TABLE ticket_tag_links (ticket_id TEXT, tag_id INTEGER);
            CREATE TABLE ticket_feedback (ticket_id TEXT, rating INTEGER);
            CREATE TABLE action_proposals (ticket_id TEXT, proposal TEXT);
            CREATE TABLE ticket_counters (name TEXT PRIMARY KEY, next_value INTEGER);
            CREATE TABLE support_articles (title TEXT);
            INSERT INTO tickets(ticket_id, issue) VALUES ('TK009999', 'old ticket');
            INSERT INTO messages(ticket_id, message, attachments_json)
                VALUES ('TK009999', 'old message', '[]');
            INSERT INTO ticket_notes VALUES ('TK009999', 'old note');
            INSERT INTO ticket_tag_links VALUES ('TK009999', 1);
            INSERT INTO ticket_feedback VALUES ('TK009999', 5);
            INSERT INTO action_proposals VALUES ('TK009999', 'old proposal');
            INSERT INTO ticket_counters VALUES ('ticket_id', 10000);
            INSERT INTO support_articles VALUES ('Keep this article');
        """)

    removed, ids = replace_with_demo_tickets(path)
    assert removed == 1
    assert ids == [f"TK{number:06d}" for number in range(1, 6)]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM tickets WHERE issue LIKE '[DEMO]%' ").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM tickets WHERE customer_email LIKE '%@example.com'").fetchone()[0] == 5
        for table in ("ticket_notes", "ticket_tag_links", "ticket_feedback", "action_proposals"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert connection.execute("SELECT next_value FROM ticket_counters WHERE name='ticket_id'").fetchone()[0] == 6
        assert connection.execute("SELECT title FROM support_articles").fetchone()[0] == "Keep this article"

    removed_again, ids_again = replace_with_demo_tickets(path)
    assert removed_again == 5
    assert ids_again == ids


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        replace_with_demo_tickets(path)
    assert not path.exists()
