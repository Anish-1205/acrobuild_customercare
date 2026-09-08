import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import {
  createAdminArticle,
  createAdminKnowledgeDocument,
  getAdminArticles,
  getAdminKnowledgeDocuments,
  getSupportAssist,
  uploadAdminKnowledgeDocuments,
  updateAdminArticle,
  updateAdminKnowledgeDocument
} from "../lib/api";
import type {
  KnowledgeDocumentRecord,
  SupportArticleRecord,
  SupportAssistResponse
} from "../types";

type ArticlesPageProps = {
  embedded?: boolean;
};

type ArticleDraft = {
  body: string;
  category: string;
  id: number | null;
  keywords: string[];
  status: SupportArticleRecord["status"];
  summary: string;
  title: string;
  url: string;
};

type KnowledgeDocumentDraft = {
  body: string;
  category: string;
  id: number | null;
  source_name: string;
  source_type: string;
  status: KnowledgeDocumentRecord["status"];
  summary: string;
  tags: string[];
  title: string;
};

function emptyArticleDraft(): ArticleDraft {
  return {
    body: "",
    category: "Support",
    id: null,
    keywords: [],
    status: "Draft",
    summary: "",
    title: "New article",
    url: ""
  };
}

function emptyKnowledgeDocumentDraft(): KnowledgeDocumentDraft {
  return {
    body: "",
    category: "Knowledge",
    id: null,
    source_name: "",
    source_type: "manual",
    status: "Draft",
    summary: "",
    tags: [],
    title: "New training document"
  };
}

function articleToDraft(article: SupportArticleRecord): ArticleDraft {
  return {
    body: article.body || "",
    category: article.category || "Support",
    id: article.id,
    keywords: [...(article.keywords || [])],
    status: article.status || "Draft",
    summary: article.summary || "",
    title: article.title || "New article",
    url: article.url || ""
  };
}

function knowledgeDocumentToDraft(document: KnowledgeDocumentRecord): KnowledgeDocumentDraft {
  return {
    body: document.body || "",
    category: document.category || "Knowledge",
    id: document.id,
    source_name: document.source_name || "",
    source_type: document.source_type || "manual",
    status: document.status || "Draft",
    summary: document.summary || "",
    tags: [...(document.tags || [])],
    title: document.title || "New training document"
  };
}

function articlePreviewCopy(article: ArticleDraft) {
  return article.body.trim() || article.summary.trim() || "Add article content to preview it here.";
}

function knowledgePreviewCopy(document: KnowledgeDocumentDraft) {
  return document.body.trim() || document.summary.trim() || "Add training content to preview it here.";
}

function buildImportedDocumentTitle(fileName: string) {
  const normalizedName = fileName.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();

  return normalizedName || "Imported training document";
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
        return;
      }

      reject(new Error("The selected file could not be read."));
    };
    reader.onerror = () => reject(new Error("The selected file could not be read."));
    reader.readAsDataURL(file);
  });
}

export function ArticlesPage({ embedded = false }: ArticlesPageProps) {
  const [articles, setArticles] = useState<SupportArticleRecord[]>([]);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocumentRecord[]>([]);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState<"All" | SupportArticleRecord["status"]>("All");
  const [knowledgeSearch, setKnowledgeSearch] = useState("");
  const [knowledgeCategoryFilter, setKnowledgeCategoryFilter] = useState("All");
  const [knowledgeStatusFilter, setKnowledgeStatusFilter] = useState<
    "All" | KnowledgeDocumentRecord["status"]
  >("All");
  const [draft, setDraft] = useState<ArticleDraft>(emptyArticleDraft());
  const [knowledgeDraft, setKnowledgeDraft] = useState<KnowledgeDocumentDraft>(
    emptyKnowledgeDocumentDraft()
  );
  const [isWorking, setIsWorking] = useState(false);
  const [isAssistWorking, setIsAssistWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [assistQuery, setAssistQuery] = useState("");
  const [assistResponse, setAssistResponse] = useState<SupportAssistResponse | null>(null);
  const [surface, setSurface] = useState<"list" | "manage-article" | "manage-document">("list");

  async function loadArticles() {
    const response = await getAdminArticles();
    setArticles(response.articles);
  }

  async function loadKnowledgeDocuments() {
    const response = await getAdminKnowledgeDocuments();
    setKnowledgeDocuments(response.documents);
  }

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setError("");
        const [articleResponse, documentResponse] = await Promise.all([
          getAdminArticles(),
          getAdminKnowledgeDocuments()
        ]);

        if (cancelled) {
          return;
        }

        setArticles(articleResponse.articles);
        setKnowledgeDocuments(documentResponse.documents);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load the knowledge workspace.");
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, []);

  const categoryOptions = useMemo(() => {
    const values = new Set(["All"]);

    for (const article of articles) {
      if (article.category.trim()) {
        values.add(article.category);
      }
    }

    return [...values].sort((left, right) => left.localeCompare(right));
  }, [articles]);

  const knowledgeCategoryOptions = useMemo(() => {
    const values = new Set(["All"]);

    for (const document of knowledgeDocuments) {
      if (document.category.trim()) {
        values.add(document.category);
      }
    }

    return [...values].sort((left, right) => left.localeCompare(right));
  }, [knowledgeDocuments]);

  const filteredArticles = useMemo(() => {
    const searchValue = search.trim().toLowerCase();

    return articles.filter((article) => {
      const matchesCategory = categoryFilter === "All" || article.category === categoryFilter;
      const matchesStatus = statusFilter === "All" || article.status === statusFilter;
      const matchesSearch =
        !searchValue ||
        `${article.title} ${article.summary} ${article.body} ${article.category} ${article.keywords.join(" ")}`
          .toLowerCase()
          .includes(searchValue);

      return matchesCategory && matchesStatus && matchesSearch;
    });
  }, [articles, categoryFilter, search, statusFilter]);

  const filteredKnowledgeDocuments = useMemo(() => {
    const searchValue = knowledgeSearch.trim().toLowerCase();

    return knowledgeDocuments.filter((document) => {
      const matchesCategory =
        knowledgeCategoryFilter === "All" || document.category === knowledgeCategoryFilter;
      const matchesStatus =
        knowledgeStatusFilter === "All" || document.status === knowledgeStatusFilter;
      const matchesSearch =
        !searchValue ||
        `${document.title} ${document.summary} ${document.body} ${document.category} ${
          document.source_name
        } ${document.tags.join(" ")}`
          .toLowerCase()
          .includes(searchValue);

      return matchesCategory && matchesStatus && matchesSearch;
    });
  }, [
    knowledgeCategoryFilter,
    knowledgeDocuments,
    knowledgeSearch,
    knowledgeStatusFilter
  ]);

  function openCreateArticle() {
    setDraft(emptyArticleDraft());
    setSurface("manage-article");
    setError("");
  }

  function openEditArticle(article: SupportArticleRecord) {
    setDraft(articleToDraft(article));
    setSurface("manage-article");
    setError("");
  }

  function openCreateKnowledgeDocument() {
    setKnowledgeDraft(emptyKnowledgeDocumentDraft());
    setSurface("manage-document");
    setError("");
  }

  function openEditKnowledgeDocument(document: KnowledgeDocumentRecord) {
    setKnowledgeDraft(knowledgeDocumentToDraft(document));
    setSurface("manage-document");
    setError("");
  }

  async function handleSaveArticle() {
    try {
      setIsWorking(true);
      setError("");
      setNotice("");

      const payload = {
        body: draft.body,
        category: draft.category,
        keywords: draft.keywords,
        status: draft.status,
        summary: draft.summary,
        title: draft.title,
        url: draft.url
      };

      if (draft.id) {
        await updateAdminArticle(draft.id, payload);
      } else {
        await createAdminArticle(payload);
      }

      await loadArticles();
      setSurface("list");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save article.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveKnowledgeDocument() {
    try {
      setIsWorking(true);
      setError("");
      setNotice("");

      const payload = {
        body: knowledgeDraft.body,
        category: knowledgeDraft.category,
        source_name: knowledgeDraft.source_name,
        source_type: knowledgeDraft.source_type,
        status: knowledgeDraft.status,
        summary: knowledgeDraft.summary,
        tags: knowledgeDraft.tags,
        title: knowledgeDraft.title
      };

      if (knowledgeDraft.id) {
        await updateAdminKnowledgeDocument(knowledgeDraft.id, payload);
      } else {
        await createAdminKnowledgeDocument(payload);
      }

      await loadKnowledgeDocuments();
      setSurface("list");
    } catch (saveError) {
      setError(
        saveError instanceof Error ? saveError.message : "Unable to save the training document."
      );
    } finally {
      setIsWorking(false);
    }
  }

  async function handleKnowledgeFileImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    try {
      const fileText = (await file.text()).trim();

      setKnowledgeDraft((current) => ({
        ...current,
        body: fileText,
        source_name: file.name,
        source_type: "upload",
        summary: current.summary || fileText.slice(0, 220),
        title:
          current.id || current.title !== "New training document"
            ? current.title
            : buildImportedDocumentTitle(file.name)
      }));
      setError("");
      setNotice("");
    } catch {
      setError("That file could not be read. Try a text, markdown, CSV, or JSON file.");
    } finally {
      event.target.value = "";
    }
  }

  async function handleKnowledgeFilesUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);

    if (!files.length) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setNotice("");
      const encodedFiles = await Promise.all(
        files.map(async (file) => ({
          content_base64: await readFileAsDataUrl(file),
          mime_type: file.type,
          name: file.name
        }))
      );
      const response = await uploadAdminKnowledgeDocuments({
        category: "Knowledge",
        files: encodedFiles,
        source_name: "",
        status: "Draft",
        tags: []
      });

      await loadKnowledgeDocuments();
      setNotice(
        `${response.documents.length} training document${
          response.documents.length === 1 ? "" : "s"
        } imported from ${files.length} file${files.length === 1 ? "" : "s"}.`
      );
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Unable to upload the training files right now."
      );
    } finally {
      event.target.value = "";
      setIsWorking(false);
    }
  }

  async function handleRunAssistPreview() {
    const cleanedQuery = assistQuery.trim();

    if (!cleanedQuery) {
      setError("Add a sample customer question to preview the AI agent.");
      return;
    }

    try {
        setIsAssistWorking(true);
        setError("");
        setNotice("");
        const response = await getSupportAssist({
          issue: cleanedQuery,
          limit: 3
      });
      setAssistResponse(response);
    } catch (previewError) {
      setError(
        previewError instanceof Error
          ? previewError.message
          : "Unable to generate an AI preview right now."
      );
    } finally {
      setIsAssistWorking(false);
    }
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Knowledge Base</div>
          <h2>AI Training Workspace</h2>
          <p>
            Train the support agent with published articles, uploaded training notes, and a live AI
            preview before customers see the answer.
          </p>
        </section>
      ) : null}

      {error ? <div className="banner-error">{error}</div> : null}
      {notice ? <div className="banner-success">{notice}</div> : null}

      {surface === "list" ? (
        <>
          <section className="plain-card workspace-directory-shell">
            <div className="workspace-directory-header">
              <div>
                <div className="section-title">Article Library</div>
                <div className="section-copy">
                  {filteredArticles.length} saved support articles used for customer guidance
                </div>
              </div>

              <button
                className="primary-button management-plus-button"
                onClick={openCreateArticle}
                type="button"
              >
                <span>+</span>
                New article
              </button>
            </div>

            <div className="filter-grid articles-filter-grid">
              <input
                className="rail-search"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search articles by title, summary, or keyword"
                value={search}
              />

              <select
                className="field-input"
                onChange={(event) => setCategoryFilter(event.target.value)}
                value={categoryFilter}
              >
                {categoryOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>

              <select
                className="field-input"
                onChange={(event) =>
                  setStatusFilter(event.target.value as "All" | SupportArticleRecord["status"])
                }
                value={statusFilter}
              >
                <option value="All">All statuses</option>
                <option value="Published">Published</option>
                <option value="Draft">Draft</option>
              </select>
            </div>

            <div className="workspace-directory-grid">
              {filteredArticles.map((article) => (
                <article className="workspace-record-card article-record-card" key={article.id}>
                  <div className="workspace-record-icon">A</div>
                  <div className="workspace-record-main">
                    <div className="workspace-record-title-row">
                      <strong>{article.title}</strong>
                    </div>
                    <div className="workspace-record-copy">
                      {article.summary || "Support guidance article"}
                    </div>
                    <div className="badge-row compact workspace-record-tag-row">
                      <span className="badge-chip dark">
                        <span className="badge-dot" style={{ backgroundColor: "#38bdf8" }} />
                        {article.category}
                      </span>
                      {article.keywords.slice(0, 2).map((keyword) => (
                        <span className="badge-chip dark" key={keyword}>
                          {keyword}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="workspace-record-meta article-record-meta">
                    <span className="schedule-pill article-record-status">{article.status}</span>
                    <button
                      className="ghost-button small workspace-record-manage article-record-manage"
                      onClick={() => openEditArticle(article)}
                      type="button"
                    >
                      Manage
                    </button>
                  </div>
                </article>
              ))}

              {!filteredArticles.length ? (
                <div className="empty-card">No articles matched the current filters.</div>
              ) : null}
            </div>
          </section>

          <section className="plain-card workspace-directory-shell">
            <div className="workspace-directory-header">
              <div>
                <div className="section-title">Training Documents</div>
                <div className="section-copy">
                  {filteredKnowledgeDocuments.length} reusable notes uploaded by admins and owners
                </div>
              </div>

              <div className="workspace-detail-actions">
                <label className="ghost-button" style={{ cursor: isWorking ? "wait" : "pointer" }}>
                  Upload files
                  <input
                    accept=".txt,.md,.markdown,.csv,.json,.html,.htm,.docx"
                    disabled={isWorking}
                    hidden
                    multiple
                    onChange={(event) => void handleKnowledgeFilesUpload(event)}
                    type="file"
                  />
                </label>
                <button
                  className="primary-button management-plus-button"
                  onClick={openCreateKnowledgeDocument}
                  type="button"
                >
                  <span>+</span>
                  New training doc
                </button>
              </div>
            </div>

            <div className="filter-grid articles-filter-grid">
              <input
                className="rail-search"
                onChange={(event) => setKnowledgeSearch(event.target.value)}
                placeholder="Search uploaded notes, SOPs, FAQs, or policies"
                value={knowledgeSearch}
              />

              <select
                className="field-input"
                onChange={(event) => setKnowledgeCategoryFilter(event.target.value)}
                value={knowledgeCategoryFilter}
              >
                {knowledgeCategoryOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>

              <select
                className="field-input"
                onChange={(event) =>
                  setKnowledgeStatusFilter(
                    event.target.value as "All" | KnowledgeDocumentRecord["status"]
                  )
                }
                value={knowledgeStatusFilter}
              >
                <option value="All">All statuses</option>
                <option value="Published">Published</option>
                <option value="Draft">Draft</option>
              </select>
            </div>

            <div className="workspace-directory-grid">
              {filteredKnowledgeDocuments.map((document) => (
                <article className="workspace-record-card article-record-card" key={document.id}>
                  <div className="workspace-record-icon">K</div>
                  <div className="workspace-record-main">
                    <div className="workspace-record-title-row">
                      <strong>{document.title}</strong>
                    </div>
                    <div className="workspace-record-copy">
                      {document.summary || "Training note for the AI support agent"}
                    </div>
                    <div className="badge-row compact workspace-record-tag-row">
                      <span className="badge-chip dark">
                        <span className="badge-dot" style={{ backgroundColor: "#14b8a6" }} />
                        {document.category}
                      </span>
                      {document.source_name ? (
                        <span className="badge-chip dark">{document.source_name}</span>
                      ) : null}
                      {document.tags.slice(0, 2).map((tag) => (
                        <span className="badge-chip dark" key={tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="workspace-record-meta article-record-meta">
                    <span className="schedule-pill article-record-status">{document.status}</span>
                    <button
                      className="ghost-button small workspace-record-manage article-record-manage"
                      onClick={() => openEditKnowledgeDocument(document)}
                      type="button"
                    >
                      Manage
                    </button>
                  </div>
                </article>
              ))}

              {!filteredKnowledgeDocuments.length ? (
                <div className="empty-card">
                  No training documents matched the current filters.
                </div>
              ) : null}
            </div>
          </section>

          <section className="plain-card workspace-detail-shell">
            <div className="workspace-detail-topbar">
              <div>
                <div className="workspace-detail-kicker">AI assistant preview</div>
                <div className="section-title">Test the trained support agent</div>
                <div className="section-copy">
                  Run a sample customer question against the current articles and uploaded training
                  docs before publishing changes.
                </div>
              </div>

              <div className="workspace-detail-actions">
                <button
                  className="primary-button"
                  disabled={isAssistWorking}
                  onClick={() => void handleRunAssistPreview()}
                  type="button"
                >
                  {isAssistWorking ? "Thinking..." : "Preview AI answer"}
                </button>
              </div>
            </div>

            <label className="field-block">
              <span>Sample customer question</span>
              <textarea
                className="field-textarea short"
                onChange={(event) => setAssistQuery(event.target.value)}
                placeholder="Example: My order is late and I want to know whether I can get a replacement or a refund."
                rows={4}
                value={assistQuery}
              />
            </label>

            <div className="plain-card inset">
              <div className="section-title small">Assistant answer</div>
              <div className="preview-shell">
                {assistResponse?.answer || "Preview an answer to inspect how the AI uses your workspace guidance."}
              </div>

              {assistResponse ? (
                <>
                  <div className="tag-cloud">
                    <span className="badge-chip dark">{assistResponse.source_label}</span>
                    <span className="badge-chip dark">
                      {assistResponse.used_llm ? assistResponse.model || "Qwen" : "Fallback response"}
                    </span>
                    {assistResponse.retrieval_mode ? (
                      <span className="badge-chip dark">{assistResponse.retrieval_mode}</span>
                    ) : null}
                    {assistResponse.confidence_label ? (
                      <span className="badge-chip dark">{assistResponse.confidence_label} confidence</span>
                    ) : null}
                    {assistResponse.handoff_recommended ? (
                      <span className="badge-chip dark">Human handoff suggested</span>
                    ) : null}
                    {assistResponse.assist_error ? (
                      <span className="badge-chip dark">LLM fallback used</span>
                    ) : null}
                  </div>

                  <div className="selection-list">
                    <div className="selection-row">
                      <span>
                        <strong>Knowledge documents used</strong>
                        <small>
                          {assistResponse.knowledge_documents.length
                            ? assistResponse.knowledge_documents.map((document) => document.title).join(", ")
                            : "No published training documents were matched for this question."}
                        </small>
                      </span>
                    </div>
                    <div className="selection-row">
                      <span>
                        <strong>Published articles linked</strong>
                        <small>
                          {assistResponse.articles.length
                            ? assistResponse.articles.map((article) => article.title).join(", ")
                            : "No article links were suggested for this question."}
                        </small>
                      </span>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </section>
        </>
      ) : surface === "manage-article" ? (
        <section className="plain-card workspace-detail-shell">
          <div className="workspace-detail-topbar">
            <div>
              <div className="workspace-detail-kicker">Article workspace</div>
              <div className="section-title">{draft.id ? "Manage article" : "Create article"}</div>
              <div className="section-copy">
                Published articles are linked back into the customer-facing AI assistant.
              </div>
            </div>

            <div className="workspace-detail-actions">
              <button className="ghost-button" onClick={() => setSurface("list")} type="button">
                Back to library
              </button>
              <button
                className="primary-button"
                disabled={isWorking}
                onClick={() => void handleSaveArticle()}
                type="button"
              >
                Save article
              </button>
            </div>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Title</span>
              <input
                className="field-input"
                onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
                value={draft.title}
              />
            </label>

            <label className="field-block">
              <span>Category</span>
              <input
                className="field-input"
                onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))}
                value={draft.category}
              />
            </label>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Status</span>
              <select
                className="field-input"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    status: event.target.value as SupportArticleRecord["status"]
                  }))
                }
                value={draft.status}
              >
                <option value="Published">Published</option>
                <option value="Draft">Draft</option>
              </select>
            </label>

            <label className="field-block">
              <span>Article URL</span>
              <input
                className="field-input"
                onChange={(event) => setDraft((current) => ({ ...current, url: event.target.value }))}
                placeholder="https://support.example.com/article"
                value={draft.url}
              />
            </label>
          </div>

          <label className="field-block">
            <span>Summary</span>
            <textarea
              className="field-textarea short"
              onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))}
              rows={3}
              value={draft.summary}
            />
          </label>

          <label className="field-block">
            <span>Keywords</span>
            <input
              className="field-input"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  keywords: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean)
                }))
              }
              placeholder="refund, delivery, subscription"
              value={draft.keywords.join(", ")}
            />
          </label>

          <label className="field-block">
            <span>Body</span>
            <textarea
              className="field-textarea tall"
              onChange={(event) => setDraft((current) => ({ ...current, body: event.target.value }))}
              value={draft.body}
            />
          </label>

          <div className="plain-card inset">
            <div className="section-title small">Article preview</div>
            <div className="preview-shell">{articlePreviewCopy(draft)}</div>
            <div className="tag-cloud">
              <span className="badge-chip dark">{draft.category || "Support"}</span>
              {draft.keywords.map((keyword) => (
                <span className="badge-chip dark" key={keyword}>
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        </section>
      ) : (
        <section className="plain-card workspace-detail-shell">
          <div className="workspace-detail-topbar">
            <div>
              <div className="workspace-detail-kicker">Training workspace</div>
              <div className="section-title">
                {knowledgeDraft.id ? "Manage training document" : "Create training document"}
              </div>
              <div className="section-copy">
                Upload or paste reusable guidance so the AI agent learns your internal support
                rules, SOPs, and policy notes.
              </div>
            </div>

            <div className="workspace-detail-actions">
              <button className="ghost-button" onClick={() => setSurface("list")} type="button">
                Back to workspace
              </button>
              <button
                className="primary-button"
                disabled={isWorking}
                onClick={() => void handleSaveKnowledgeDocument()}
                type="button"
              >
                Save training doc
              </button>
            </div>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Title</span>
              <input
                className="field-input"
                onChange={(event) =>
                  setKnowledgeDraft((current) => ({ ...current, title: event.target.value }))
                }
                value={knowledgeDraft.title}
              />
            </label>

            <label className="field-block">
              <span>Category</span>
              <input
                className="field-input"
                onChange={(event) =>
                  setKnowledgeDraft((current) => ({ ...current, category: event.target.value }))
                }
                value={knowledgeDraft.category}
              />
            </label>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Status</span>
              <select
                className="field-input"
                onChange={(event) =>
                  setKnowledgeDraft((current) => ({
                    ...current,
                    status: event.target.value as KnowledgeDocumentRecord["status"]
                  }))
                }
                value={knowledgeDraft.status}
              >
                <option value="Published">Published</option>
                <option value="Draft">Draft</option>
              </select>
            </label>

            <label className="field-block">
              <span>Source type</span>
              <select
                className="field-input"
                onChange={(event) =>
                  setKnowledgeDraft((current) => ({
                    ...current,
                    source_type: event.target.value
                  }))
                }
                value={knowledgeDraft.source_type}
              >
                <option value="manual">Manual note</option>
                <option value="upload">Uploaded file</option>
                <option value="policy">Policy</option>
                <option value="playbook">Playbook</option>
              </select>
            </label>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Source name</span>
              <input
                className="field-input"
                onChange={(event) =>
                  setKnowledgeDraft((current) => ({
                    ...current,
                    source_name: event.target.value
                  }))
                }
                placeholder="Delivery escalation SOP.md"
                value={knowledgeDraft.source_name}
              />
            </label>

            <label className="field-block">
              <span>Import text file</span>
              <input
                accept=".txt,.md,.csv,.json"
                className="field-input"
                onChange={(event) => void handleKnowledgeFileImport(event)}
                type="file"
              />
            </label>
          </div>

          <label className="field-block">
            <span>Summary</span>
            <textarea
              className="field-textarea short"
              onChange={(event) =>
                setKnowledgeDraft((current) => ({
                  ...current,
                  summary: event.target.value
                }))
              }
              rows={3}
              value={knowledgeDraft.summary}
            />
          </label>

          <label className="field-block">
            <span>Tags</span>
            <input
              className="field-input"
              onChange={(event) =>
                setKnowledgeDraft((current) => ({
                  ...current,
                  tags: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean)
                }))
              }
              placeholder="refund policy, VIP handling, logistics"
              value={knowledgeDraft.tags.join(", ")}
            />
          </label>

          <label className="field-block">
            <span>Training content</span>
            <textarea
              className="field-textarea tall"
              onChange={(event) =>
                setKnowledgeDraft((current) => ({
                  ...current,
                  body: event.target.value
                }))
              }
              placeholder="Paste the internal note, SOP, FAQ, or policy text here."
              value={knowledgeDraft.body}
            />
          </label>

          <div className="plain-card inset">
            <div className="section-title small">Training document preview</div>
            <div className="preview-shell">{knowledgePreviewCopy(knowledgeDraft)}</div>
            <div className="tag-cloud">
              <span className="badge-chip dark">{knowledgeDraft.category || "Knowledge"}</span>
              <span className="badge-chip dark">{knowledgeDraft.source_type || "manual"}</span>
              {knowledgeDraft.tags.map((tag) => (
                <span className="badge-chip dark" key={tag}>
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

