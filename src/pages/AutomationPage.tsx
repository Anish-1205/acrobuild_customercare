import { useEffect, useState } from "react";
import { StaffPageHeader } from "../components/StaffPageHeader";
import {
  type ActionProposal,
  type AgentCapacity,
  type EscalationTicket,
  confirmTicketAction,
  getAutomationDashboard,
  proposeTicketAction
} from "../lib/api";
import "../automation.css";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The automation request could not be completed.";
}

export function AutomationPage() {
  const [tickets, setTickets] = useState<EscalationTicket[]>([]);
  const [agents, setAgents] = useState<AgentCapacity[]>([]);
  const [proposal, setProposal] = useState<ActionProposal | null>(null);
  const [ticket, setTicket] = useState("");
  const [agent, setAgent] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");

  async function refresh() {
    const data = await getAutomationDashboard();
    setTickets(data.tickets);
    setAgents(data.agents);
  }

  useEffect(() => {
    void refresh()
      .catch((loadError) => setError(errorMessage(loadError)))
      .finally(() => setLoading(false));
  }, []);

  async function preview(kind: "assign" | "status", value: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setProposal(await proposeTicketAction(ticket, kind, value));
    } catch (previewError) {
      setError(errorMessage(previewError));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!proposal) return;
    setBusy(true);
    setError("");
    try {
      await confirmTicketAction(proposal.proposal_id);
      setProposal(null);
      setNotice("Ticket change confirmed and saved.");
      await refresh();
    } catch (confirmationError) {
      setError(errorMessage(confirmationError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="automation-page stack-page">
      <StaffPageHeader
        description="Review escalation and capacity data, prepare one proposed ticket change, then confirm it explicitly before anything is saved."
        eyebrow="Manager workflow"
        title="Automation"
      />

      <div aria-live="polite" aria-atomic="true">
        {loading ? <div className="phase6-status" role="status">Loading escalation and capacity data...</div> : null}
        {error ? <div className="phase6-status" role="alert">{error}</div> : null}
        {notice ? <div className="phase6-status" role="status">{notice}</div> : null}
      </div>

      <section className="plain-card automation-section" aria-labelledby="automation-overdue-heading">
        <div className="automation-section-head">
          <div>
            <h2 id="automation-overdue-heading">Overdue tickets</h2>
            <p>Elapsed-time thresholds: High 4 hours, Medium 24 hours, Low 72 hours.</p>
          </div>
          <span className="soft-pill">{tickets.length} overdue</span>
        </div>
        {tickets.length ? (
          <div className="phase6-table-wrap">
            <table>
              <caption className="sr-only">Tickets currently beyond their escalation threshold</caption>
              <thead><tr><th scope="col">Ticket</th><th scope="col">Priority</th><th scope="col">Assigned to</th><th scope="col">Age</th></tr></thead>
              <tbody>{tickets.map((item) => (
                <tr key={item.ticket_id}>
                  <td><button aria-pressed={ticket === item.ticket_id} className="automation-ticket-button" onClick={() => { setTicket(item.ticket_id); setProposal(null); }} type="button">{item.ticket_id}</button></td>
                  <td>{item.priority}</td><td>{item.assigned_agent || "Unassigned"}</td><td>{Math.floor(item.age_hours)}h</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : !loading ? <div className="empty-card">No overdue tickets.</div> : null}
      </section>

      <section className="plain-card automation-section" aria-labelledby="automation-capacity-heading">
        <div className="automation-section-head">
          <div><h2 id="automation-capacity-heading">Team capacity</h2><p>Current active-ticket counts and available capacity returned by the automation API.</p></div>
        </div>
        {agents.length ? (
          <ul className="automation-capacity-list">
            {agents.map((item) => <li key={item.name}><div><strong>{item.name}</strong><span>{item.team}</span></div><span>{item.active_tickets} active</span><b>{item.available_capacity} available</b></li>)}
          </ul>
        ) : !loading ? <div className="empty-card">No capacity records are available.</div> : null}
      </section>

      <section className="plain-card automation-section" aria-labelledby="automation-review-heading">
        <div className="automation-section-head">
          <div><h2 id="automation-review-heading">Review a ticket change</h2><p>Previewing creates an expiring proposal only. The ticket is unchanged until Confirm change is selected.</p></div>
        </div>
        <div className="editor-grid">
          <label className="field-block"><span>Ticket ID</span><input className="field-input" value={ticket} onChange={(event) => { setTicket(event.target.value); setProposal(null); }} /></label>
          <label className="field-block"><span>Agent</span><select className="field-input" value={agent} onChange={(event) => { setAgent(event.target.value); setProposal(null); }}><option value="">Choose an agent</option>{agents.filter((item) => item.available_capacity > 0).map((item) => <option key={item.name}>{item.name}</option>)}</select></label>
        </div>
        <div className="action-row wrap">
          <button className="primary-button" disabled={busy || !ticket || !agent} onClick={() => void preview("assign", agent)} type="button">Preview assignment</button>
          <button className="ghost-button" disabled={busy || !ticket} onClick={() => void preview("status", "Resolved")} type="button">Preview resolution</button>
        </div>
        {proposal ? (
          <div className="automation-proposal" role="region" aria-label="Proposed change">
            <div className="phase6-kicker">Confirmation required</div>
            <h3>Review proposal for {proposal.ticket_id}</h3>
            <dl>{Object.entries(proposal.change).map(([key, value]) => <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd><span>{proposal.before[key] || "Not set"}</span><b aria-hidden="true">→</b><strong>{value}</strong></dd></div>)}</dl>
            <p>This proposal expires in {Math.max(1, Math.ceil(proposal.expires_in / 60))} minutes and has not changed the ticket yet.</p>
            <div className="action-row wrap"><button className="primary-button" disabled={busy} onClick={() => void confirm()} type="button">Confirm change</button><button className="ghost-button" disabled={busy} onClick={() => setProposal(null)} type="button">Cancel proposal</button></div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
