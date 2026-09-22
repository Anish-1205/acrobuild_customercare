import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  clearApiActivity,
  getApiActivity,
  subscribeToApiActivity,
  type ApiActivityRecord
} from "../lib/apiActivity";
import type { RagEvaluation } from "../types";
import "../api-activity.css";

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function requestOf(record: ApiActivityRecord) {
  return (record.request || {}) as Record<string, unknown>;
}

function responseOf(record: ApiActivityRecord) {
  return (record.response || {}) as Record<string, unknown>;
}

function questionOf(record: ApiActivityRecord) {
  return String(requestOf(record).issue || "Chatbot message");
}

function answerOf(record: ApiActivityRecord) {
  if (record.status === "pending") return "The chatbot is preparing the answer.";
  return String(responseOf(record).answer || "No answer was returned.");
}

const METRIC_LABELS: Record<string, string> = {
  answer_relevance: "Answer relevance",
  context_precision: "Context precision",
  context_recall: "Context recall",
  groundedness: "Groundedness",
  hallucination_risk: "Hallucination risk",
  mrr: "MRR",
  ndcg: "NDCG",
  overall_quality: "Overall quality",
  retrieval_hit_rate: "Retrieval hit rate"
};

function evaluationOf(record: ApiActivityRecord) {
  return responseOf(record).rag_evaluation as RagEvaluation | undefined;
}

function statusText(record: ApiActivityRecord) {
  if (record.status === "pending") return "Answering";
  if (record.status === "failed") return "Failed";
  return "Answered";
}

export function ApiActivityPage({ basePath = "/home" }: { basePath?: "/home" | "/admin" }) {
  const [records, setRecords] = useState<ApiActivityRecord[]>(getApiActivity);
  const [selectedId, setSelectedId] = useState(records[0]?.id || "");

  useEffect(() => subscribeToApiActivity(() => setRecords(getApiActivity())), []);
  useEffect(() => {
    if (!records.some((record) => record.id === selectedId)) setSelectedId(records[0]?.id || "");
  }, [records, selectedId]);

  const selected = useMemo(
    () => records.find((record) => record.id === selectedId) || records[0],
    [records, selectedId]
  );

  return (
    <main className="api-activity-page">
      <header className="api-activity-topbar">
        <div>
          <span className="api-activity-eyebrow">Acrobuild support</span>
          <h1>Chatbot activity</h1>
          <p>See how a customer question became an answer.</p>
        </div>
        <Link className="api-activity-button" to="/home#help">Open chatbot</Link>
      </header>

      <nav aria-label="Chatbot activity views" className="api-view-tabs">
        <Link aria-current="page" className="active" to={`${basePath}/api-activity`}><b>1</b><span><strong>Chat request</strong><small>Question, chatbot API, and answer</small></span></Link>
        <Link to={`${basePath}/data-api-logs`}><b>2</b><span><strong>Property data used</strong><small>Live Acrobuild lookups inside the answer</small></span></Link>
      </nav>

      <section className="api-page-guide">
        <strong>What this page shows</strong>
        <span>A customer asks a question</span><i>→</i><span>The chatbot API processes it</span><i>→</i><span>The answer returns to chat</span>
      </section>

      <section className="api-activity-workspace">
        <aside className="api-activity-list">
          <div className="api-activity-list-head"><strong>Recent questions</strong><span>{records.length}</span></div>
          {records.length ? records.map((record) => (
            <button
              className={`api-activity-row${record.id === selected?.id ? " active" : ""}`}
              key={record.id}
              onClick={() => setSelectedId(record.id)}
              type="button"
            >
              <span className={`api-activity-status ${record.status}`} />
              <span className="api-activity-row-copy">
                <strong>{questionOf(record)}</strong>
                <small>{formatTime(record.startedAt)}</small>
              </span>
              <b>{statusText(record)}</b>
            </button>
          )) : <div className="api-activity-empty"><strong>No questions yet</strong><span>Open the chatbot and ask a question. It will appear here automatically.</span></div>}
        </aside>

        <article className="api-activity-detail">
          {selected ? (
            <>
              <header className="api-detail-title">
                <div><span>Selected conversation</span><h2>{questionOf(selected)}</h2></div>
                <span className={`api-activity-pill ${selected.status}`}>{statusText(selected)}</span>
              </header>

              <section className="api-request-flow">
                <article>
                  <span className="api-step-label"><b>1</b> Customer question</span>
                  <p>{questionOf(selected)}</p>
                </article>
                <span className="api-flow-arrow">→</span>
                <article>
                  <span className="api-step-label"><b>2</b> Chatbot API</span>
                  <code>{selected.method} {selected.endpoint}</code>
                  <small>{selected.durationMs ?? "-"} ms</small>
                </article>
                <span className="api-flow-arrow">→</span>
                <article className="answer">
                  <span className="api-step-label"><b>3</b> Answer shown</span>
                  <p>{answerOf(selected)}</p>
                </article>
              </section>

              {evaluationOf(selected) ? (
                <section className="rag-evaluation-panel">
                  <header>
                    <div><span>RAG evaluation</span><h3>Answer quality signals</h3></div>
                    <em>Online proxy metrics</em>
                  </header>
                  <p className="rag-evaluation-note">These scores are calculated automatically for this answer. Metrics marked N/A require a labelled evaluation dataset.</p>
                  <div className="rag-metric-grid">
                    {Object.entries(evaluationOf(selected)?.metrics ?? {}).map(([key, metric]) => (
                      <article className={`rag-metric-card ${metric.status}`} key={key} title={metric.explanation}>
                        <span>{METRIC_LABELS[key] ?? key.replace(/_/g, " ")}</span>
                        <strong>{metric.percent === null ? "N/A" : `${metric.percent}%`}</strong>
                        <small>{metric.status === "not_available" ? "Needs labelled data" : metric.status}</small>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <Link className="api-next-link" to={`${basePath}/data-api-logs`}>
                <span><strong>Want to see the live property data?</strong><small>Open the APIs used inside this answer.</small></span>
                <b>View property data →</b>
              </Link>

              {selected.error ? <section className="api-simple-error"><strong>Request error</strong><p>{selected.error}</p></section> : null}

              <details className="api-technical-details">
                <summary>Technical details (for developers)</summary>
                <section className="api-activity-code-section"><h3>Request</h3><pre>{formatJson(selected.request)}</pre></section>
                {selected.response ? <section className="api-activity-code-section"><h3>Response</h3><pre>{formatJson(selected.response)}</pre></section> : null}
              </details>
            </>
          ) : <div className="api-activity-detail-empty"><strong>Select a question</strong><span>The request and answer will appear here.</span></div>}
        </article>
      </section>

      <button className="api-clear-link" onClick={() => clearApiActivity()} type="button">Clear activity history</button>
    </main>
  );
}
