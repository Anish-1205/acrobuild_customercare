import type { Ticket } from "../types";

export type KnowledgeArticle = {
  body: string;
  category: string;
  id: number;
  keywords: string[];
  status: "Published" | "Draft";
  summary: string;
  title: string;
  url: string;
};

export const knowledgeArticles: KnowledgeArticle[] = [
  {
    id: 1,
    title: "Site visit booking checklist",
    category: "Site Visit",
    status: "Published",
    summary: "How to confirm visit requests, collect key details, and set expectations for scheduling.",
    url: "",
    keywords: ["site visit", "inspection", "sample flat", "tour", "visit"],
    body: [
      "When a buyer asks for a site visit, confirm the project name, preferred date or time, and the best callback number before routing the request.",
      "",
      "Capture whether they want a sample flat tour, construction walkthrough, or a general sales visit so the operations team has enough detail to schedule correctly.",
      "",
      "If the preferred slot is not confirmed yet, explain that the team will review availability and respond with the next scheduling update instead of promising an exact slot immediately.",
      "",
      "The goal is to make the request easy to action while setting clear expectations for the next step."
    ].join("\n")
  },
  {
    id: 2,
    title: "Quotation and inventory follow-up playbook",
    category: "Sales",
    status: "Published",
    summary: "Quotation guidance, inventory checks, and sales follow-up steps for active projects.",
    url: "",
    keywords: ["quotation", "pricing", "availability", "inventory", "brochure"],
    body: [
      "Use this guide when a buyer asks for pricing, unit availability, brochures, or a quotation for an Acrobuild project.",
      "",
      "Confirm the project, property type, budget range, and whether the buyer wants residential, commercial, villa, or plot options so the sales team receives the right context.",
      "",
      "If live inventory is not immediately available, explain that the request will be reviewed and a confirmed follow-up will be shared rather than guessing availability.",
      "",
      "Keep the reply clear about what was requested and what the team will confirm next."
    ].join("\n")
  },
  {
    id: 3,
    title: "Payment receipts and ledger clarification",
    category: "Payments",
    status: "Published",
    summary: "Payment acknowledgement, receipt checks, and finance escalation guidance.",
    url: "",
    keywords: ["payment", "receipt", "invoice", "ledger", "installment"],
    body: [
      "This article covers payment receipts, invoice questions, ledger clarifications, and installment follow-up before escalation to project finance.",
      "",
      "Confirm the project, unit or booking reference, amount paid, payment date, and the exact concern so the finance team can review the right transaction.",
      "",
      "If a receipt or ledger entry is missing, explain that the payment will be reviewed and reconciled before the team confirms the outcome.",
      "",
      "Avoid promising a final correction until the finance review is complete."
    ].join("\n")
  },
  {
    id: 4,
    title: "Construction progress update playbook",
    category: "Construction",
    status: "Published",
    summary: "Guidance for progress questions, milestone updates, and delay follow-up.",
    url: "",
    keywords: ["construction", "progress", "milestone", "timeline", "delay"],
    body: [
      "Construction updates should stay aligned with approved milestone information shared by the project team.",
      "",
      "When a buyer asks about progress, confirm the project or tower reference and explain the latest verified milestone instead of offering a guessed completion date.",
      "",
      "If there is a known delay, note that the update will be reviewed and the buyer will be given the latest confirmed timeline or next milestone guidance.",
      "",
      "The response should stay factual, calm, and free of unverified promises."
    ].join("\n")
  },
  {
    id: 5,
    title: "Legal documents and registration checklist",
    category: "Documentation",
    status: "Published",
    summary: "Checklist guidance for legal, registration, and buyer-document requests.",
    url: "",
    keywords: ["agreement", "registration", "approval", "noc", "kyc"],
    body: [
      "Use this article for agreement requests, approvals, NOC, registration, KYC-linked documents, and other paperwork support.",
      "",
      "Ask for the project name, booking reference, and the exact document needed before routing the request to the documentation team.",
      "",
      "If the request depends on verification or project-stage approval, explain that the team will confirm document readiness after review.",
      "",
      "Clear document naming and buyer details reduce back-and-forth and speed up resolution."
    ].join("\n")
  },
  {
    id: 6,
    title: "Handover and maintenance triage guide",
    category: "Handover",
    status: "Published",
    summary: "Triage guidance for possession, snag, and maintenance support.",
    url: "",
    keywords: ["handover", "possession", "maintenance", "defect", "snag"],
    body: [
      "Handover and maintenance cases should capture the project name, tower or unit reference, and photo or video evidence where available.",
      "",
      "If the request involves possession timelines, snag lists, leakage, electrical issues, or other defects, record the exact concern before escalation.",
      "",
      "Safety-sensitive issues should be flagged for urgent review rather than handled as a standard callback.",
      "",
      "The care team should receive enough detail to act without asking the buyer to repeat the entire issue."
    ].join("\n")
  },
  {
    id: 7,
    title: "Business-hours and after-hours expectations",
    category: "Operations",
    status: "Published",
    summary: "Sets reply-time expectations for requests raised outside the normal support window.",
    url: "",
    keywords: ["after hours", "business hours", "response time", "sla"],
    body: [
      "For after-hours requests, let buyers know their message has been received and queued for the next active support window.",
      "",
      "Do not imply that a specialist is already reviewing the case if the team is offline. Instead, set a clear expectation for when the next response window begins.",
      "",
      "If the request involves urgent payment, construction, or safety-sensitive maintenance concerns, note that it may be escalated based on severity.",
      "",
      "The goal is to confirm the request was captured while avoiding overpromising an immediate resolution."
    ].join("\n")
  }
];

function normalizeText(value: string) {
  return value.trim().toLowerCase();
}

function buildSearchBlob(ticket: Pick<Ticket, "business_hours_tag" | "intent_tag" | "issue" | "issue_type" | "priority" | "queue_name" | "status">) {
  return normalizeText(
    [
      ticket.issue_type,
      ticket.intent_tag,
      ticket.issue,
      ticket.priority,
      ticket.status,
      ticket.queue_name,
      ticket.business_hours_tag
    ]
      .filter(Boolean)
      .join(" ")
  );
}

export function getRelatedArticlesForTicket(ticket: Pick<Ticket, "business_hours_tag" | "intent_tag" | "issue" | "issue_type" | "priority" | "queue_name" | "status">) {
  const blob = buildSearchBlob(ticket);

  return [...knowledgeArticles]
    .map((article) => ({
      article,
      score: article.keywords.reduce(
        (total, keyword) => (blob.includes(normalizeText(keyword)) ? total + 1 : total),
        0
      )
    }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => right.score - left.score || left.article.title.localeCompare(right.article.title))
    .map(({ article }) => article)
    .slice(0, 3);
}

export function buildAiReplyFromTicket(
  ticket: Pick<Ticket, "business_hours_tag" | "intent_tag" | "issue" | "issue_type" | "priority" | "queue_name" | "status">,
  customerName: string
) {
  const relatedArticles = getRelatedArticlesForTicket(ticket);
  const topArticle = relatedArticles[0];
  const issueType = ticket.issue_type || "support";
  const intent = ticket.intent_tag || "request";
  const coverageLine =
    ticket.business_hours_tag === "After Hours"
      ? "Our team has your request queued and the next active support window will continue the review."
      : "Our team is actively reviewing the request and will keep you updated with the next action.";

  const articleLine = topArticle
    ? `We are following our "${topArticle.title}" guidance so the response stays consistent.`
    : "We are checking the project details and the best next step for you.";

  return [
    `Hi ${customerName},`,
    "",
    `Thanks for reaching out about your ${intent.toLowerCase()} in ${issueType.toLowerCase()}.`,
    coverageLine,
    articleLine,
    "",
    "If you need anything else in the meantime, reply here and our team will help."
  ].join("\n");
}