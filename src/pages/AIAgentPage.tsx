import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRole } from "../contexts/RoleContext";
import {
  createAdminArticle,
  deleteAdminKnowledgeDocuments,
  getAdminArticles,
  getAdminKnowledgeDocuments,
  getSupportAssist,
  importAdminKnowledgeUrl,
  uploadAdminKnowledgeDocuments
} from "../lib/api";
import { getRolePanelPath } from "../lib/roleNavigation";
import type {
  KnowledgeDocumentRecord,
  SupportArticleRecord,
  SupportAssistResponse
} from "../types";

type AIAgentPageProps = {
  embedded?: boolean;
};

type IntegratedLinkItem = {
  document_count: number;
  document_ids: number[];
  key: string;
  page_count: number;
  page_source_names: string[];
  source_name: string;
  source_type: string;
  title: string;
  updated_at?: string;
};

function normalizeSourceType(value: string) {
  return value.trim().toLowerCase();
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      resolve(String(reader.result || ""));
    };

    reader.onerror = () => {
      reject(new Error(`Unable to read ${file.name}.`));
    };

    reader.readAsDataURL(file);
  });
}

function buildSummary(text: string, maxLength = 170) {
  const cleanedText = text.replace(/\s+/g, " ").trim();

  if (!cleanedText) {
    return "";
  }

  if (cleanedText.length <= maxLength) {
    return cleanedText;
  }

  return `${cleanedText.slice(0, maxLength - 3).trimEnd()}...`;
}

function getTimeValue(value?: string) {
  const timestamp = Date.parse(value || "");
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function isLinkSourceType(sourceType: string) {
  const normalizedSourceType = normalizeSourceType(sourceType);

  return (
    normalizedSourceType === "url" ||
    normalizedSourceType === "urls" ||
    normalizedSourceType === "store-website" ||
    normalizedSourceType === "website" ||
    normalizedSourceType === "site"
  );
}

function getWebsiteGroupName(sourceName: string) {
  try {
    const parsedUrl = new URL(sourceName);
    const normalizedHost = parsedUrl.hostname.replace(/^www\./i, "").toLowerCase();
    const hostParts = normalizedHost.split(".").filter(Boolean);
    let groupedHost = normalizedHost;

    if (hostParts.length >= 3) {
      const topLevelSegment = hostParts[hostParts.length - 1] || "";
      const secondLevelSegment = hostParts[hostParts.length - 2] || "";
      const usesCountrySuffix =
        topLevelSegment.length === 2 && secondLevelSegment.length <= 3;

      groupedHost = usesCountrySuffix
        ? hostParts.slice(-3).join(".")
        : hostParts.slice(-2).join(".");
    }

    return `${parsedUrl.protocol}//${groupedHost}`;
  } catch {
    return sourceName.trim();
  }
}

function getIntegratedLinkGroupKey(sourceType: string, sourceName: string) {
  const normalizedSourceType = normalizeSourceType(sourceType);
  const groupedSourceName = getWebsiteGroupName(sourceName);

  return `${normalizedSourceType}:${groupedSourceName.toLowerCase()}`;
}

function buildKnowledgeCounts(documents: KnowledgeDocumentRecord[]) {
  const fileSources = new Set<string>();
  const linkSources = new Set<string>();
  const noteSources = new Set<string>();

  for (const document of documents) {
    const sourceType = normalizeSourceType(document.source_type || "manual");
    const sourceKey = `${sourceType}:${document.source_name || document.title || document.id}`;

    if (sourceType === "upload") {
      fileSources.add(sourceKey);
      continue;
    }

    if (
      sourceType === "url" ||
      sourceType === "urls" ||
      sourceType === "store-website" ||
      sourceType === "website" ||
      sourceType === "site"
    ) {
      linkSources.add(
        getIntegratedLinkGroupKey(
          sourceType,
          document.source_name || document.title || String(document.id)
        )
      );
      continue;
    }

    noteSources.add(sourceKey);
  }

  return {
    files: fileSources.size,
    links: linkSources.size,
    notes: noteSources.size
  };
}

function buildIntegratedLinkItems(documents: KnowledgeDocumentRecord[]) {
  const groupedLinks = new Map<string, IntegratedLinkItem>();

  for (const document of documents) {
    const sourceType = normalizeSourceType(document.source_type || "");
    const sourceName = document.source_name.trim();

    if (!isLinkSourceType(sourceType) || !sourceName) {
      continue;
    }

    const groupedSourceName = getWebsiteGroupName(sourceName);
    const groupKey = getIntegratedLinkGroupKey(sourceType, sourceName);
    const existingGroup = groupedLinks.get(groupKey);
    const documentUpdatedAt = document.updated_at || document.created_at;

    if (!existingGroup) {
      groupedLinks.set(groupKey, {
        document_count: 1,
        document_ids: [document.id],
        key: groupKey,
        page_count: 1,
        page_source_names: [sourceName.toLowerCase()],
        source_name: groupedSourceName,
        source_type: sourceType,
        title: document.title.trim() || groupedSourceName,
        updated_at: documentUpdatedAt
      });
      continue;
    }

    existingGroup.document_count += 1;
    existingGroup.document_ids.push(document.id);

    if (!existingGroup.page_source_names.includes(sourceName.toLowerCase())) {
      existingGroup.page_source_names.push(sourceName.toLowerCase());
      existingGroup.page_count += 1;
    }

    if (getTimeValue(documentUpdatedAt) > getTimeValue(existingGroup.updated_at)) {
      existingGroup.title = document.title.trim() || groupedSourceName;
      existingGroup.updated_at = documentUpdatedAt;
    }
  }

  return Array.from(groupedLinks.values()).sort((left, right) => {
    const timestampDifference = getTimeValue(right.updated_at) - getTimeValue(left.updated_at);

    if (timestampDifference !== 0) {
      return timestampDifference;
    }

    return left.source_name.localeCompare(right.source_name);
  });
}

function formatIntegratedLinkDate(value?: string) {
  if (!getTimeValue(value)) {
    return "Updated recently";
  }

  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric"
  }).format(new Date(value as string));
}

function getIntegratedLinkTypeLabel(sourceType: string) {
  return normalizeSourceType(sourceType) === "store-website" ? "Website" : "Website";
}

export function AIAgentPage({ embedded = false }: AIAgentPageProps) {
  const navigate = useNavigate();
  const { role } = useRole();
  const [documents, setDocuments] = useState<KnowledgeDocumentRecord[]>([]);
  const [articles, setArticles] = useState<SupportArticleRecord[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadInputVersion, setUploadInputVersion] = useState(0);
  const [urlValue, setUrlValue] = useState("");
  const [urlLabel, setUrlLabel] = useState("");
  const [answerTitle, setAnswerTitle] = useState("");
  const [answerBody, setAnswerBody] = useState("");
  const [testQuestion, setTestQuestion] = useState("");
  const [assistResponse, setAssistResponse] = useState<SupportAssistResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploadingFiles, setIsUploadingFiles] = useState(false);
  const [isImportingUrl, setIsImportingUrl] = useState(false);
  const [isSavingAnswer, setIsSavingAnswer] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isDeletingLinks, setIsDeletingLinks] = useState(false);
  const [selectedIntegratedLinkKeys, setSelectedIntegratedLinkKeys] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  async function loadTrainingData(showLoader = true) {
    try {
      if (showLoader) {
        setIsLoading(true);
      }

      setErrorMessage("");

      const [documentResponse, articleResponse] = await Promise.all([
        getAdminKnowledgeDocuments(),
        getAdminArticles()
      ]);

      setDocuments(documentResponse.documents);
      setArticles(articleResponse.articles);
    } catch (loadError) {
      setErrorMessage(
        loadError instanceof Error ? loadError.message : "Could not load the AI Agent page."
      );
    } finally {
      if (showLoader) {
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadTrainingData();
  }, []);

  const publishedDocuments = useMemo(
    () => documents.filter((document) => document.status === "Published"),
    [documents]
  );
  const publishedArticles = useMemo(
    () => articles.filter((article) => article.status === "Published"),
    [articles]
  );
  const knowledgeCounts = useMemo(
    () => buildKnowledgeCounts(publishedDocuments),
    [publishedDocuments]
  );
  const integratedLinkItems = useMemo(
    () => buildIntegratedLinkItems(publishedDocuments),
    [publishedDocuments]
  );
  const readyCount =
    knowledgeCounts.files + knowledgeCounts.links + knowledgeCounts.notes + publishedArticles.length;
  const matchedChunks = assistResponse?.matched_chunks?.slice(0, 4) ?? [];
  const allIntegratedLinkKeys = useMemo(
    () => integratedLinkItems.map((item) => item.key),
    [integratedLinkItems]
  );
  const hasSelectedAllIntegratedLinks =
    integratedLinkItems.length > 0 &&
    allIntegratedLinkKeys.every((itemKey) => selectedIntegratedLinkKeys.includes(itemKey));
  const selectedIntegratedLinksCount = selectedIntegratedLinkKeys.filter((itemKey) =>
    allIntegratedLinkKeys.includes(itemKey)
  ).length;

  useEffect(() => {
    setSelectedIntegratedLinkKeys((currentSelection) =>
      currentSelection.filter((itemKey) => allIntegratedLinkKeys.includes(itemKey))
    );
  }, [allIntegratedLinkKeys]);

  function clearFeedback() {
    setErrorMessage("");
    setSuccessMessage("");
  }

  function toggleIntegratedLinkSelection(itemKey: string) {
    setSelectedIntegratedLinkKeys((currentSelection) =>
      currentSelection.includes(itemKey)
        ? currentSelection.filter((selectionKey) => selectionKey !== itemKey)
        : [...currentSelection, itemKey]
    );
  }

  function toggleAllIntegratedLinks() {
    setSelectedIntegratedLinkKeys(
      hasSelectedAllIntegratedLinks ? [] : allIntegratedLinkKeys
    );
  }

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFiles(Array.from(event.target.files || []));
  }

  async function handleUploadFiles() {
    if (!selectedFiles.length) {
      setErrorMessage("Choose one PDF or file first.");
      return;
    }

    try {
      clearFeedback();
      setIsUploadingFiles(true);

      const response = await uploadAdminKnowledgeDocuments({
        category: "Knowledge",
        files: await Promise.all(
          selectedFiles.map(async (file) => ({
            content_base64: await readFileAsDataUrl(file),
            mime_type: file.type || "",
            name: file.name
          }))
        ),
        status: "Published",
        tags: []
      });

      setSelectedFiles([]);
      setUploadInputVersion((currentValue) => currentValue + 1);
      setSuccessMessage(
        response.files[0]?.warning ||
          `${response.files.length} file${response.files.length === 1 ? "" : "s"} added. The AI can use them now.`
      );
      await loadTrainingData(false);
    } catch (uploadError) {
      setErrorMessage(uploadError instanceof Error ? uploadError.message : "Could not upload the file.");
    } finally {
      setIsUploadingFiles(false);
    }
  }

  async function handleImportUrl() {
    if (!urlValue.trim()) {
      setErrorMessage("Paste one website URL first.");
      return;
    }

    try {
      clearFeedback();
      setIsImportingUrl(true);

      const response = await importAdminKnowledgeUrl({
        category: "Knowledge",
        status: "Published",
        tags: [],
        title_prefix: urlLabel.trim(),
        url: urlValue.trim()
      });

      setUrlValue("");
      setUrlLabel("");
      setSuccessMessage(
        response.warning || "Website page added. The chat box can use it now."
      );
      await loadTrainingData(false);
    } catch (importError) {
      setErrorMessage(importError instanceof Error ? importError.message : "Could not import the URL.");
    } finally {
      setIsImportingUrl(false);
    }
  }

  async function handleSaveAnswer() {
    if (!answerBody.trim()) {
      setErrorMessage("Type the answer before saving.");
      return;
    }

    try {
      clearFeedback();
      setIsSavingAnswer(true);

      await createAdminArticle({
        body: answerBody.trim(),
        category: "Support",
        keywords: [],
        status: "Published",
        summary: buildSummary(answerBody),
        title: answerTitle.trim() || "Quick answer",
        url: ""
      });

      setAnswerTitle("");
      setAnswerBody("");
      setSuccessMessage("Answer saved. The AI can use it now.");
      await loadTrainingData(false);
    } catch (saveError) {
      setErrorMessage(saveError instanceof Error ? saveError.message : "Could not save the answer.");
    } finally {
      setIsSavingAnswer(false);
    }
  }

  async function handleTestQuestion() {
    if (!testQuestion.trim()) {
      setErrorMessage("Ask one question first.");
      return;
    }

    try {
      clearFeedback();
      setIsTesting(true);
      setAssistResponse(
        await getSupportAssist({
          issue: testQuestion.trim(),
          limit: 4,
          prefer_fast_response: false
        })
      );
    } catch (testError) {
      setErrorMessage(testError instanceof Error ? testError.message : "Could not test the AI.");
    } finally {
      setIsTesting(false);
    }
  }

  async function handleDeleteIntegratedLinks(linkKeys: string[]) {
    const targetLinks = integratedLinkItems.filter((item) => linkKeys.includes(item.key));
    const documentIds = Array.from(
      new Set(targetLinks.flatMap((item) => item.document_ids))
    );

    if (!documentIds.length) {
      setErrorMessage("Select at least one integrated link first.");
      return;
    }

    const shouldDelete = window.confirm(
      documentIds.length === 1
        ? "Delete this integrated link from the AI knowledge base?"
        : `Delete ${targetLinks.length} integrated links from the AI knowledge base?`
    );

    if (!shouldDelete) {
      return;
    }

    try {
      clearFeedback();
      setIsDeletingLinks(true);

      const response = await deleteAdminKnowledgeDocuments(documentIds);

      setSelectedIntegratedLinkKeys((currentSelection) =>
        currentSelection.filter((itemKey) => !linkKeys.includes(itemKey))
      );
      setSuccessMessage(
        response.deleted_count === 1
          ? "Integrated link deleted."
          : `${response.deleted_count} saved link records deleted.`
      );
      await loadTrainingData(false);
    } catch (deleteError) {
      setErrorMessage(
        deleteError instanceof Error ? deleteError.message : "Could not delete the integrated link."
      );
    } finally {
      setIsDeletingLinks(false);
    }
  }

  return (
    <div className="teach-ai-page">
      <section className="teach-ai-hero">
        <div className="teach-ai-hero-copy">
          <div className="teach-ai-kicker">{embedded ? "Teach AI" : "AI Agent"}</div>
          <h1>Teach your AI in one simple page</h1>
          <p>
            Upload a PDF or file, add a website link, type an answer, then ask a
            question. The same knowledge is used by your customer chat box.
          </p>

          <div className="teach-ai-hero-actions">
            <button
              className="teach-ai-primary-button"
              onClick={() => navigate(getRolePanelPath(role, "chat-widget"))}
              type="button"
            >
              Open chat box settings
            </button>
            <div className="teach-ai-inline-note">
              If the answer works here, it will work in the chat box too.
            </div>
          </div>
        </div>

        <div className="teach-ai-hero-side">
          <div className="teach-ai-hero-visual-card">
            <div className="teach-ai-hero-visual-head">
              <div>
                <div className="teach-ai-visual-kicker">Knowledge loop</div>
                <strong>Teach once, answer everywhere</strong>
              </div>
              <div className="teach-ai-hero-visual-pill">
                {isLoading ? "Syncing" : `${readyCount} ready`}
              </div>
            </div>

            <div className="teach-ai-hero-flow">
              <article className="teach-ai-hero-flow-step accent-cyan">
                <span>1</span>
                <strong>Add source</strong>
                <small>Upload a file, paste a URL, or type a reply.</small>
              </article>
              <article className="teach-ai-hero-flow-step accent-amber">
                <span>2</span>
                <strong>Shape the answer</strong>
                <small>Turn raw knowledge into a reusable support response.</small>
              </article>
              <article className="teach-ai-hero-flow-step accent-violet">
                <span>3</span>
                <strong>Test the outcome</strong>
                <small>Ask a real customer question before it reaches the chat box.</small>
              </article>
            </div>

            <div className="teach-ai-hero-signal-row">
              <div className="teach-ai-hero-signal-card">
                <span>Chat box</span>
                <strong>Uses the same knowledge</strong>
              </div>
              <div className="teach-ai-hero-signal-card">
                <span>Team handoff</span>
                <strong>Only when confidence is low</strong>
              </div>
            </div>
          </div>

          <div className="teach-ai-stat-grid">
            <div className="teach-ai-stat-card">
              <span>Ready now</span>
              <strong>{isLoading ? "..." : readyCount}</strong>
              <small>things your AI can already use</small>
            </div>
            <div className="teach-ai-stat-card">
              <span>Files</span>
              <strong>{isLoading ? "..." : knowledgeCounts.files}</strong>
              <small>PDF or document uploads</small>
            </div>
            <div className="teach-ai-stat-card">
              <span>Links</span>
              <strong>{isLoading ? "..." : knowledgeCounts.links}</strong>
              <small>website pages and URLs</small>
            </div>
            <div className="teach-ai-stat-card">
              <span>Answers</span>
              <strong>{isLoading ? "..." : publishedArticles.length}</strong>
              <small>typed by your team</small>
            </div>
          </div>
        </div>
      </section>

      {errorMessage ? <div className="teach-ai-feedback error">{errorMessage}</div> : null}
      {successMessage ? <div className="teach-ai-feedback success">{successMessage}</div> : null}

      <section className="teach-ai-card-grid">
        <article className="teach-ai-card">
          <div className="teach-ai-card-head">
            <div className="teach-ai-step-badge">1</div>
            <div>
              <h2>Upload PDF or file</h2>
              <p>Add training from PDF, DOCX, TXT, CSV, JSON, or HTML files.</p>
            </div>
          </div>

          <input
            accept=".pdf,.docx,.txt,.md,.markdown,.csv,.json,.html,.htm"
            className="teach-ai-file-input"
            key={uploadInputVersion}
            multiple
            onChange={handleFileSelection}
            type="file"
          />

          {selectedFiles.length ? (
            <div className="teach-ai-file-list">
              {selectedFiles.map((file) => (
                <div className="teach-ai-file-chip" key={`${file.name}-${file.lastModified}`}>
                  {file.name}
                </div>
              ))}
            </div>
          ) : (
            <div className="teach-ai-help-text">Best for menus, policies, and product PDFs.</div>
          )}

          <button
            className="teach-ai-primary-button"
            disabled={isUploadingFiles}
            onClick={() => void handleUploadFiles()}
            type="button"
          >
            {isUploadingFiles ? "Uploading..." : "Upload and teach AI"}
          </button>
        </article>

        <article className="teach-ai-card">
          <div className="teach-ai-card-head">
            <div className="teach-ai-step-badge">2</div>
            <div>
              <h2>Add website URL</h2>
              <p>Paste one page link. We will read the page and save it for the AI.</p>
            </div>
          </div>

          <label className="teach-ai-field">
            <span>Website URL</span>
            <input
              className="teach-ai-input"
              onChange={(event) => setUrlValue(event.target.value)}
              placeholder="https://your-site.com/page"
              value={urlValue}
            />
          </label>

          <label className="teach-ai-field">
            <span>Short name (optional)</span>
            <input
              className="teach-ai-input"
              onChange={(event) => setUrlLabel(event.target.value)}
              placeholder="Shipping page"
              value={urlLabel}
            />
          </label>

          <button
            className="teach-ai-primary-button"
            disabled={isImportingUrl}
            onClick={() => void handleImportUrl()}
            type="button"
          >
            {isImportingUrl ? "Reading page..." : "Add URL"}
          </button>
        </article>

        <article className="teach-ai-card">
          <div className="teach-ai-card-head">
            <div className="teach-ai-step-badge">3</div>
            <div>
              <h2>Type answer yourself</h2>
              <p>Write one simple answer you want the AI to say to customers.</p>
            </div>
          </div>

          <label className="teach-ai-field">
            <span>Answer title</span>
            <input
              className="teach-ai-input"
              onChange={(event) => setAnswerTitle(event.target.value)}
              placeholder="Delivery answer"
              value={answerTitle}
            />
          </label>

          <label className="teach-ai-field">
            <span>Answer</span>
            <textarea
              className="teach-ai-textarea"
              onChange={(event) => setAnswerBody(event.target.value)}
              placeholder="Example: If the order is late, first say sorry, then ask for the order number."
              rows={6}
              value={answerBody}
            />
          </label>

          <button
            className="teach-ai-primary-button"
            disabled={isSavingAnswer}
            onClick={() => void handleSaveAnswer()}
            type="button"
          >
            {isSavingAnswer ? "Saving..." : "Save answer"}
          </button>
        </article>

        <article className="teach-ai-card teach-ai-test-card">
          <div className="teach-ai-card-head">
            <div className="teach-ai-step-badge">4</div>
            <div>
              <h2>Ask the AI</h2>
              <p>Test one customer question. This uses the same answer flow as your chat box.</p>
            </div>
          </div>

          <label className="teach-ai-field">
            <span>Customer question</span>
            <textarea
              className="teach-ai-textarea"
              onChange={(event) => setTestQuestion(event.target.value)}
              placeholder="My order is late. What should I do?"
              rows={5}
              value={testQuestion}
            />
          </label>

          <button
            className="teach-ai-primary-button"
            disabled={isTesting}
            onClick={() => void handleTestQuestion()}
            type="button"
          >
            {isTesting ? "Thinking..." : "Ask AI now"}
          </button>

          {assistResponse ? (
            <div className="teach-ai-answer-shell">
              <div className="teach-ai-answer-label">AI answer</div>
              <div className="teach-ai-answer-copy">{assistResponse.answer}</div>

              <div className="teach-ai-answer-meta">
                <span>Source: {assistResponse.source_label || "AI knowledge"}</span>
                <span>
                  {assistResponse.handoff_recommended
                    ? "A person should check this answer."
                    : "No handoff needed."}
                </span>
              </div>

              {matchedChunks.length ? (
                <div className="teach-ai-match-list">
                  {matchedChunks.map((chunk) => (
                    <div
                      className="teach-ai-match-chip"
                      key={`${chunk.record_id}-${chunk.chunk_id}`}
                    >
                      <strong>{chunk.title}</strong>
                      <span>{chunk.source_name || chunk.source_type}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </article>
      </section>

      <section className="teach-ai-library-card">
        <div className="teach-ai-library-head">
          <div>
            <div className="teach-ai-kicker">Integrated Links</div>
            <h2>Links already connected to your AI</h2>
            <p>
              These are the website links your AI can already use. You can select all,
              delete one, or delete multiple at once.
            </p>
          </div>

          <div className="teach-ai-library-actions">
            <label className="teach-ai-select-all">
              <input
                checked={hasSelectedAllIntegratedLinks}
                onChange={toggleAllIntegratedLinks}
                type="checkbox"
              />
              <span>Select all</span>
            </label>

            <button
              className="teach-ai-secondary-button"
              disabled={!selectedIntegratedLinksCount || isDeletingLinks}
              onClick={() => void handleDeleteIntegratedLinks(selectedIntegratedLinkKeys)}
              type="button"
            >
              {isDeletingLinks
                ? "Deleting..."
                : `Delete selected${selectedIntegratedLinksCount ? ` (${selectedIntegratedLinksCount})` : ""}`}
            </button>
          </div>
        </div>

        {integratedLinkItems.length ? (
          <div className="teach-ai-source-list teach-ai-source-list-scroll">
            {integratedLinkItems.map((item) => (
              <div className="teach-ai-source-row" key={item.key}>
                <label className="teach-ai-source-check">
                  <input
                    checked={selectedIntegratedLinkKeys.includes(item.key)}
                    onChange={() => toggleIntegratedLinkSelection(item.key)}
                    type="checkbox"
                  />
                </label>

                <div className="teach-ai-source-body">
                  <strong>{item.source_name}</strong>
                  <span>
                    {item.page_count} integrated page{item.page_count === 1 ? "" : "s"} from this
                    website.
                  </span>
                </div>

                <div className="teach-ai-source-meta">
                  <span>{getIntegratedLinkTypeLabel(item.source_type)}</span>
                  <span>
                    {item.document_count} saved part{item.document_count === 1 ? "" : "s"}
                  </span>
                  <span>{formatIntegratedLinkDate(item.updated_at)}</span>
                </div>

                <div className="teach-ai-source-actions">
                  <button
                    className="teach-ai-danger-button"
                    disabled={isDeletingLinks}
                    onClick={() => void handleDeleteIntegratedLinks([item.key])}
                    type="button"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="teach-ai-empty-state">
            No integrated links yet. Add a website URL above and it will appear here.
          </div>
        )}
      </section>
    </div>
  );
}

