import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getApiActivity, subscribeToApiActivity, type ApiActivityRecord } from "../lib/apiActivity";
import type { DataApiCallTrace } from "../types";
import "../api-activity.css";

function responseOf(record: ApiActivityRecord) {
  return (record.response || {}) as Record<string, unknown>;
}
function requestOf(record: ApiActivityRecord) {
  return (record.request || {}) as Record<string, unknown>;
}
function callsOf(record: ApiActivityRecord) {
  const calls = responseOf(record).data_api_calls;
  return Array.isArray(calls) ? calls as DataApiCallTrace[] : [];
}
function questionOf(record: ApiActivityRecord) {
  return String(requestOf(record).issue || "Chatbot question");
}
function explainEndpoint(endpoint: string) {
  if (endpoint === "/api/cs/company") return "Company profile and contact details";
  if (endpoint === "/api/cs/projects") return "Current Acrobuild project list";
  if (endpoint.includes("/projects/") && endpoint.endsWith("/wings")) return "Wings and floor counts for the selected project";
  if (endpoint.includes("/projects/") && endpoint.endsWith("/typologies")) return "Home types, sizes, and live price ranges";
  if (endpoint.includes("/wings/") && endpoint.endsWith("/inventory")) return "Currently available flats in the selected wing";
  return "Supporting live property information";
}
function resultText(call: DataApiCallTrace) {
  const summary = call.response_summary || {};
  if (call.status === "failed") return call.error || "No data returned";
  if (call.cache_hit) return "Recent verified result reused";
  if (typeof summary.record_count === "number") return `${summary.record_count} record${summary.record_count === 1 ? "" : "s"} returned`;
  if (typeof summary.field_count === "number") return `${summary.field_count} fields returned`;
  return "Data returned successfully";
}

export function DataApiLogsPage({ basePath = "/home" }: { basePath?: "/home" | "/admin" }) {
  const [records, setRecords] = useState<ApiActivityRecord[]>(getApiActivity);
  const traceRecords = records.filter((record) => callsOf(record).length > 0);
  const [selectedId, setSelectedId] = useState(traceRecords[0]?.id || "");

  useEffect(() => subscribeToApiActivity(() => setRecords(getApiActivity())), []);
  useEffect(() => {
    if (!traceRecords.some((record) => record.id === selectedId)) setSelectedId(traceRecords[0]?.id || "");
  }, [traceRecords, selectedId]);

  const selected = useMemo(
    () => traceRecords.find((record) => record.id === selectedId) || traceRecords[0],
    [traceRecords, selectedId]
  );
  const selectedCalls = selected ? callsOf(selected) : [];

  return (
    <main className="api-activity-page">
      <header className="api-activity-topbar">
        <div>
          <span className="api-activity-eyebrow">Acrobuild support</span>
          <h1>Chatbot activity</h1>
          <p>See which verified property data was used for an answer.</p>
        </div>
        <Link className="api-activity-button" to="/home#help">Open chatbot</Link>
      </header>

      <nav aria-label="Chatbot activity views" className="api-view-tabs">
        <Link to={`${basePath}/api-activity`}><b>1</b><span><strong>Chat request</strong><small>Question, chatbot API, and answer</small></span></Link>
        <Link aria-current="page" className="active" to={`${basePath}/data-api-logs`}><b>2</b><span><strong>Property data used</strong><small>Live Acrobuild lookups inside the answer</small></span></Link>
      </nav>

      <section className="api-page-guide data-guide">
        <strong>How to read this page</strong>
        <span>Select a customer question on the left. The right side lists each Acrobuild API lookup in the order it happened.</span>
        <em>API key hidden</em>
      </section>

      <section className="api-activity-workspace">
        <aside className="api-activity-list">
          <div className="api-activity-list-head"><strong>Questions using property data</strong><span>{traceRecords.length}</span></div>
          {traceRecords.length ? traceRecords.map((record) => (
            <button className={`api-activity-row${record.id === selected?.id ? " active" : ""}`} key={record.id} onClick={() => setSelectedId(record.id)} type="button">
              <span className="api-activity-status completed" />
              <span className="api-activity-row-copy"><strong>{questionOf(record)}</strong><small>{callsOf(record).length} live lookup{callsOf(record).length === 1 ? "" : "s"}</small></span>
              <b>View</b>
            </button>
          )) : <div className="api-activity-empty"><strong>No property lookups yet</strong><span>Ask the chatbot about projects, wings, floors, flats, availability, or pricing.</span></div>}
        </aside>

        <article className="api-activity-detail">
          {selected ? (
            <>
              <header className="api-detail-title">
                <div><span>Data used to answer</span><h2>{questionOf(selected)}</h2></div>
                <span className="api-call-count">{selectedCalls.length} lookup{selectedCalls.length === 1 ? "" : "s"}</span>
              </header>

              <section className="data-api-summary">
                <strong>The chatbot checked {selectedCalls.length} live data source{selectedCalls.length === 1 ? "" : "s"}.</strong>
                <span>Each row below explains what was requested and what came back. No secret API key is displayed.</span>
              </section>

              <div className="data-api-call-list">
                {selectedCalls.map((call, index) => (
                  <article className={`data-api-call-row ${call.status}`} key={call.id}>
                    <span className="data-api-call-index">{index + 1}</span>
                    <div className="data-api-call-main">
                      <div className="data-api-call-heading"><strong>{explainEndpoint(call.endpoint)}</strong><span>{call.provider}</span></div>
                      <code>{call.method} {call.endpoint}</code>
                      {Object.keys(call.params || {}).length ? <small>Sent: {Object.entries(call.params).map(([key, value]) => `${key}: ${value}`).join(", ")}</small> : null}
                    </div>
                    <div className="data-api-call-result">
                      <b>{call.status === "failed" ? "Failed" : call.cache_hit ? "Verified cache" : "Live result"}</b>
                      <span>{resultText(call)}</span>
                      <small>{call.duration_ms} ms</small>
                    </div>
                  </article>
                ))}
              </div>

              <Link className="api-back-link" to={`${basePath}/api-activity`}>← Back to the question and final answer</Link>
            </>
          ) : <div className="api-activity-detail-empty"><strong>No property data selected</strong><span>Ask a property question in the chatbot, then return here.</span></div>}
        </article>
      </section>
    </main>
  );
}
