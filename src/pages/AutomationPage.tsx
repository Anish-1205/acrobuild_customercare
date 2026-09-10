import { useEffect, useState } from "react";
import { ActionProposal, AgentCapacity, EscalationTicket, confirmTicketAction, getAutomationDashboard, proposeTicketAction } from "../lib/api";
import "../automation.css";

export function AutomationPage() {
  const [tickets, setTickets] = useState<EscalationTicket[]>([]);
  const [agents, setAgents] = useState<AgentCapacity[]>([]);
  const [proposal, setProposal] = useState<ActionProposal | null>(null);
  const [ticket, setTicket] = useState("");
  const [agent, setAgent] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  async function refresh() {
    const data = await getAutomationDashboard();
    setTickets(data.tickets);
    setAgents(data.agents);
  }
  useEffect(() => { void refresh().catch(e => setError(String(e))); }, []);
  async function preview(kind: "assign" | "status", value: string) {
    setBusy(true); setError(""); setNotice("");
    try { setProposal(await proposeTicketAction(ticket, kind, value)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!proposal) return;
    setBusy(true); setError("");
    try { await confirmTicketAction(proposal.proposal_id); setProposal(null); setNotice("Ticket updated."); await refresh(); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  return <main className="automation-page">
    <h1>Support automations</h1>
    <p>Review overdue tickets and team capacity before confirming a change.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <section><h2>Overdue tickets</h2>
      <p>Elapsed-time thresholds: High 4 hours, Medium 24 hours, Low 72 hours.</p>
      {tickets.length ? <table><thead><tr><th>Ticket</th><th>Priority</th><th>Assigned to</th><th>Age</th></tr></thead>
        <tbody>{tickets.map(t => <tr key={t.ticket_id}><td><button onClick={() => { setTicket(t.ticket_id); setProposal(null); }}>{t.ticket_id}</button></td><td>{t.priority}</td><td>{t.assigned_agent}</td><td>{Math.floor(t.age_hours)}h</td></tr>)}</tbody></table> : <p>No overdue tickets.</p>}
    </section>
    <section><h2>Team capacity</h2><ul>{agents.map(a => <li key={a.name}>{a.name}: {a.active_tickets} active, {a.available_capacity} spaces available</li>)}</ul></section>
    <section><h2>Review a ticket change</h2>
      <label>Ticket ID <input value={ticket} onChange={e => { setTicket(e.target.value); setProposal(null); }} /></label>
      <label>Agent <select value={agent} onChange={e => { setAgent(e.target.value); setProposal(null); }}><option value="">Choose an agent</option>{agents.filter(a => a.available_capacity > 0).map(a => <option key={a.name}>{a.name}</option>)}</select></label>
      <button disabled={busy || !ticket || !agent} onClick={() => void preview("assign", agent)}>Preview assignment</button>
      <button disabled={busy || !ticket} onClick={() => void preview("status", "Resolved")}>Preview resolution</button>
      {proposal && <div role="region" aria-label="Proposed change"><p>Ticket {proposal.ticket_id}: {Object.entries(proposal.change).map(([key, value]) => `${key}: ${proposal.before[key]} → ${value}`).join(", ")}</p><p>Confirmation expires in 10 minutes.</p><button disabled={busy} onClick={() => void confirm()}>Confirm change</button><button disabled={busy} onClick={() => setProposal(null)}>Cancel</button></div>}
    </section>
  </main>;
}
