"""Reviewable workflow actions and a read-only SLA queue."""
import json
import time
from contextlib import closing
from uuid import uuid4

from services.database_service import open_database_connection


def escalation_queue(assigned_agent=None, limit=100):
    # Thresholds are elapsed hours; business-hours scheduling remains separate.
    with closing(open_database_connection()) as conn:
        import sqlite3
        conn.row_factory = sqlite3.Row
        where = " AND assigned_agent=?" if assigned_agent is not None else ""
        params = [assigned_agent] if assigned_agent is not None else []
        rows = conn.execute(
            "SELECT ticket_id,priority,assigned_agent,status,created_at, "
            "(julianday('now')-julianday(created_at))*24 AS age_hours FROM tickets "
            "WHERE status NOT IN ('Closed','Resolved')" + where +
            " AND (julianday('now')-julianday(created_at))*24 > CASE priority WHEN 'High' THEN 4 WHEN 'Medium' THEN 24 ELSE 72 END "
            "ORDER BY age_hours DESC LIMIT ?", [*params, min(limit, 500)]).fetchall()
    return [dict(row) for row in rows]


def propose_action(actor, ticket_id, kind, payload):
    if kind not in {"assign", "status"}:
        raise ValueError("Unsupported action")
    identifier = uuid4().hex
    with closing(open_database_connection()) as conn, conn:
        ticket = conn.execute("SELECT assigned_agent,status FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
        if not ticket:
            raise ValueError("Ticket not found")
        document = {"before": {"assigned_agent": ticket[0], "status": ticket[1]}, "change": payload}
        conn.execute("INSERT INTO action_proposals VALUES(?,?,?,?,?,?,0)", (identifier, actor, ticket_id, kind, json.dumps(document), time.time() + 600))
    return {"proposal_id": identifier, "ticket_id": ticket_id, "kind": kind, **document, "expires_in": 600, "confirmation_required": True}


def confirm_action(actor, proposal_id):
    with closing(open_database_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        proposal = conn.execute("SELECT ticket_id,kind,payload FROM action_proposals WHERE id=? AND actor=? AND completed=0 AND expires_at>?", (proposal_id, actor, time.time())).fetchone()
        if not proposal:
            raise ValueError("Proposal expired, already completed, or unavailable")
        ticket_id, kind, raw = proposal
        document = json.loads(raw)
        current = conn.execute("SELECT assigned_agent,status FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
        if not current or list(current) != [document["before"]["assigned_agent"], document["before"]["status"]]:
            raise ValueError("Ticket changed; preview the action again")
        column = "assigned_agent" if kind == "assign" else "status"
        value = document["change"][column]
        if kind == "assign":
            if not conn.execute("SELECT 1 FROM support_users WHERE name=? AND status='Active' AND role='agent'", (value,)).fetchone():
                raise ValueError("Choose an active agent")
        elif value not in {"Open", "Pending", "Waiting on Customer", "Resolved", "Closed"}:
            raise ValueError("Invalid ticket status")
        conn.execute(f"UPDATE tickets SET {column}=?,updated_at=CURRENT_TIMESTAMP WHERE ticket_id=?", (value, ticket_id))
        conn.execute("UPDATE action_proposals SET completed=1 WHERE id=?", (proposal_id,))
        conn.execute("INSERT INTO audit_events(event,actor,subject,metadata,created_at) VALUES(?,?,?,?,?)", ("action_confirmed", str(actor), ticket_id, json.dumps({"kind": kind, "proposal_id": proposal_id}), time.time()))
    return {"ticket_id": ticket_id, "completed": True}


def capacity_recommendations(capacity=20):
    with closing(open_database_connection()) as conn:
        rows = conn.execute("SELECT u.name,u.team,COUNT(t.ticket_id) FROM support_users u LEFT JOIN tickets t ON t.assigned_agent=u.name AND t.status NOT IN ('Closed','Resolved') WHERE u.role='agent' AND u.status='Active' GROUP BY u.id ORDER BY COUNT(t.ticket_id),u.name").fetchall()
    return [{"name": name, "team": team, "active_tickets": count, "available_capacity": max(0, capacity - count)} for name, team, count in rows]
