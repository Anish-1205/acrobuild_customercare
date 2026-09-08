import { type ChangeEvent, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { TrainHero, TrainSplitCallout } from "../components/TrainUi";
import {
  createAdminArticle,
  createAdminKnowledgeDocument,
  getAdminArticles,
  getAdminKnowledgeDocuments,
  getSupportAssist,
  importAdminKnowledgeUrl,
  updateAdminArticle,
  updateAdminKnowledgeDocument,
  uploadAdminKnowledgeDocuments
} from "../lib/api";
import type {
  KnowledgeDocumentRecord,
  SupportArticleRecord,
  SupportAssistResponse
} from "../types";

type KnowledgeBasePageProps = {
  embedded?: boolean;
};

type KnowledgeDraft = {
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

type UploadDraft = {
  category: string;
  source_name: string;
  status: KnowledgeDocumentRecord["status"];
  tags: string[];
};

type WebsiteDraft = {
  body: string;
  category: string;
  site_name: string;
  site_url: string;
  status: KnowledgeDocumentRecord["status"];
  summary: string;
  sync_scope: string;
  tags: string[];
};

type UrlImportDraft = {
  body: string;
  category: string;
  status: KnowledgeDocumentRecord["status"];
  summary: string;
  tags: string[];
  title_prefix: string;
  urls_text: string;
};

type KnowledgeCollectionId =
  | "all"
  | "guidance"
  | "help-center-articles"
  | "store-website"
  | "urls"
  | "documents";

type KnowledgeOverlayId =
  | "closed"
  | "manage-article"
  | "manage-knowledge"
  | "pick-rules"
  | "pick-sources"
  | "store-website"
  | "test"
  | "upload"
  | "urls";

type LibraryItem = {
  category: string;
  id: number;
  item_kind: Exclude<KnowledgeCollectionId, "all">;
  key: string;
  record_kind: "article" | "knowledge";
  search_text: string;
  source_label: string;
  source_name: string;
  source_type: string;
  status: "Published" | "Draft";
  summary: string;
  tags: string[];
  title: string;
  updated_at?: string;
};

function emptyKnowledgeDraft(sourceType = "manual"): KnowledgeDraft {
  const titleBySourceType: Record<string, string> = {
    manual: "New team rule",
    playbook: "New playbook",
    policy: "New policy",
    "store-website": "New website info",
    upload: "New file",
    url: "New link"
  };

  return {
    body: "",
    category: "Knowledge",
    id: null,
    source_name: "",
    source_type: sourceType,
    status: "Draft",
    summary: "",
    tags: [],
    title: titleBySourceType[sourceType] || "Team rule"
  };
}

function emptyArticleDraft(): ArticleDraft {
  return {
    body: "",
    category: "Support",
    id: null,
    keywords: [],
    status: "Draft",
    summary: "",
    title: "New customer answer",
    url: ""
  };
}

function emptyUploadDraft(): UploadDraft {
  return {
    category: "Knowledge",
    source_name: "",
    status: "Published",
    tags: []
  };
}

function emptyWebsiteDraft(): WebsiteDraft {
  return {
    body: "",
    category: "Knowledge",
    site_name: "",
    site_url: "",
    status: "Published",
    summary: "",
    sync_scope: "",
    tags: []
  };
}

function emptyUrlImportDraft(): UrlImportDraft {
  return {
    body: "",
    category: "Knowledge",
    status: "Published",
    summary: "",
    tags: [],
    title_prefix: "",
    urls_text: ""
  };
}

function knowledgeDocumentToDraft(document: KnowledgeDocumentRecord): KnowledgeDraft {
  return {
    body: document.body || "",
    category: document.category || "Knowledge",
    id: document.id,
    source_name: document.source_name || "",
    source_type: document.source_type || "manual",
    status: document.status || "Draft",
    summary: document.summary || "",
    tags: [...(document.tags || [])],
    title: document.title || "Team rule"
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
    title: article.title || "Customer answer",
    url: article.url || ""
  };
}

function articlePreviewCopy(article: ArticleDraft) {
  return article.body.trim() || article.summary.trim() || "Write the answer here and you will see a preview.";
}

function knowledgePreviewCopy(document: KnowledgeDraft) {
  return document.body.trim() || document.summary.trim() || "Write the rule here and you will see a preview.";
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

function parseCommaSeparatedList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeSourceType(value: string) {
  return value.trim().toLowerCase();
}

function getDocumentItemKind(document: KnowledgeDocumentRecord): LibraryItem["item_kind"] {
  const sourceType = normalizeSourceType(document.source_type || "manual");

  if (sourceType === "upload") {
    return "documents";
  }

  if (sourceType === "store-website" || sourceType === "website" || sourceType === "site") {
    return "store-website";
  }

  if (sourceType === "url" || sourceType === "urls") {
    return "urls";
  }

  return "guidance";
}

function getLibraryItemKey(item: LibraryItem) {
  return item.key;
}

function getSourceLabel(sourceType: string, itemKind: LibraryItem["item_kind"]) {
  if (itemKind === "documents") {
    return "File";
  }

  if (itemKind === "help-center-articles") {
    return "Customer answer";
  }

  if (itemKind === "store-website") {
    return "Website";
  }

  if (itemKind === "urls") {
    return "Link";
  }

  if (sourceType === "policy") {
    return "Team rule";
  }

  if (sourceType === "playbook") {
    return "Team rule";
  }

  return "Team rule";
}

function buildLibraryItemFromDocument(document: KnowledgeDocumentRecord): LibraryItem {
  const itemKind = getDocumentItemKind(document);
  const sourceType = normalizeSourceType(document.source_type || "manual") || "manual";

  return {
    category: document.category || "Knowledge",
    id: document.id,
    item_kind: itemKind,
    key: `knowledge-${document.id}`,
    record_kind: "knowledge",
    search_text: [
      document.title,
      document.summary,
      document.body,
      document.category,
      document.source_name,
      document.source_type,
      document.tags.join(" ")
    ]
      .join(" ")
      .toLowerCase(),
    source_label: getSourceLabel(sourceType, itemKind),
    source_name: document.source_name || "",
    source_type: sourceType,
    status: document.status,
    summary: document.summary || "",
    tags: document.tags || [],
    title: document.title || "Team rule",
    updated_at: document.updated_at || document.created_at
  };
}

function buildLibraryItemFromArticle(article: SupportArticleRecord): LibraryItem {
  return {
    category: article.category || "Support",
    id: article.id,
    item_kind: "help-center-articles",
    key: `article-${article.id}`,
    record_kind: "article",
    search_text: [
      article.title,
      article.summary,
      article.body,
      article.category,
      article.url,
      article.keywords.join(" ")
    ]
      .join(" ")
      .toLowerCase(),
    source_label: "Customer answer",
    source_name: article.url || "",
    source_type: "article",
    status: article.status,
    summary: article.summary || "",
    tags: article.keywords || [],
    title: article.title || "Customer answer",
    updated_at: article.updated_at || article.created_at
  };
}

function formatKnowledgeDate(value?: string) {
  if (!value) {
    return "--";
  }

  const parsedValue = Date.parse(value);

  if (Number.isNaN(parsedValue)) {
    return "--";
  }

  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "numeric",
    year: "numeric"
  }).format(parsedValue);
}

function formatSourceFilterLabel(value: string) {
  if (value === "All") {
    return "All types";
  }

  if (value === "upload") {
    return "File";
  }

  if (value === "manual") {
    return "Team rule";
  }

  if (value === "article") {
    return "Customer answer";
  }

  if (value === "store-website" || value === "website") {
    return "Website";
  }

  if (value === "url" || value === "urls") {
    return "Link";
  }

  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getKnowledgeItemIconLabel(item: LibraryItem) {
  if (item.item_kind === "help-center-articles") {
    return "A";
  }

  if (item.item_kind === "documents") {
    return "D";
  }

  if (item.item_kind === "store-website") {
    return "S";
  }

  if (item.item_kind === "urls") {
    return "U";
  }

  return "G";
}

function formatSourceNamePreview(item: LibraryItem) {
  const value = item.source_name.trim();

  if (!value) {
    return "";
  }

  if (value.length <= 34) {
    return value;
  }

  return `${value.slice(0, 31)}...`;
}

function getKnowledgeEditorTitle(sourceType: string, documentId: number | null) {
  const normalizedSourceType = normalizeSourceType(sourceType);
  const isEditMode = Boolean(documentId);

  if (normalizedSourceType === "store-website" || normalizedSourceType === "website") {
    return isEditMode ? "Edit website info" : "Add website info";
  }

  if (normalizedSourceType === "url" || normalizedSourceType === "urls") {
    return isEditMode ? "Edit link" : "Add link";
  }

  if (normalizedSourceType === "policy") {
    return isEditMode ? "Edit team rule" : "Add team rule";
  }

  if (normalizedSourceType === "playbook") {
    return isEditMode ? "Edit team rule" : "Add team rule";
  }

  if (normalizedSourceType === "upload") {
    return isEditMode ? "Edit file" : "Add file";
  }

  return isEditMode ? "Edit team rule" : "Add team rule";
}

function buildWebsiteKnowledgeTitle(siteName: string, siteUrl: string) {
  if (siteName.trim()) {
    return `${siteName.trim()} website info`;
  }

  try {
    return `${new URL(siteUrl).hostname} website info`;
  } catch {
    return "Website info";
  }
}

function getItemStatusLabel(status: LibraryItem["status"]) {
  return status === "Published" ? "Ready" : "Not ready";
}

function getItemStatusDescription(status: LibraryItem["status"]) {
  return status === "Published"
    ? "AI can use this now."
    : "Saved, but AI will not use this yet.";
}

function getItemTypeExplanation(item: LibraryItem) {
  if (item.item_kind === "help-center-articles") {
    return "A customer answer the AI can use again.";
  }

  if (item.item_kind === "documents") {
    return "Information taken from a file you uploaded.";
  }

  if (item.item_kind === "store-website") {
    return "Website information the AI can remember.";
  }

  if (item.item_kind === "urls") {
    return "A link the AI can use for help.";
  }

  if (item.source_type === "policy") {
    return "A private team rule for the AI.";
  }

  if (item.source_type === "playbook") {
    return "Step-by-step team help for the AI.";
  }

  return "A private team rule for the AI.";
}

export function KnowledgeBasePage({ embedded = false }: KnowledgeBasePageProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [articles, setArticles] = useState<SupportArticleRecord[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocumentRecord[]>([]);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [overlay, setOverlay] = useState<KnowledgeOverlayId>("closed");
  const [draft, setDraft] = useState<KnowledgeDraft>(emptyKnowledgeDraft());
  const [articleDraft, setArticleDraft] = useState<ArticleDraft>(emptyArticleDraft());
  const [uploadDraft, setUploadDraft] = useState<UploadDraft>(emptyUploadDraft());
  const [websiteDraft, setWebsiteDraft] = useState<WebsiteDraft>(emptyWebsiteDraft());
  const [urlImportDraft, setUrlImportDraft] = useState<UrlImportDraft>(emptyUrlImportDraft());
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadInputVersion, setUploadInputVersion] = useState(0);
  const [testIssue, setTestIssue] = useState("");
  const [assistResponse, setAssistResponse] = useState<SupportAssistResponse | null>(null);
  const [isWorking, setIsWorking] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  async function loadLibraryContent() {
    const [documentResponse, articleResponse] = await Promise.all([
      getAdminKnowledgeDocuments(),
      getAdminArticles()
    ]);

    setDocuments(documentResponse.documents);
    setArticles(articleResponse.articles);
  }

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setError("");
        const [documentResponse, articleResponse] = await Promise.all([
          getAdminKnowledgeDocuments(),
          getAdminArticles()
        ]);

        if (cancelled) {
          return;
        }

        setDocuments(documentResponse.documents);
        setArticles(articleResponse.articles);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load the knowledge base.");
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, []);

  const libraryItems = useMemo(() => {
    const items = [
      ...articles.map(buildLibraryItemFromArticle),
      ...documents.map(buildLibraryItemFromDocument)
    ];

    return items.sort((left, right) => {
      const leftTimestamp = Date.parse(left.updated_at || "");
      const rightTimestamp = Date.parse(right.updated_at || "");

      if (Number.isNaN(leftTimestamp) && Number.isNaN(rightTimestamp)) {
        return left.title.localeCompare(right.title);
      }

      if (Number.isNaN(leftTimestamp)) {
        return 1;
      }

      if (Number.isNaN(rightTimestamp)) {
        return -1;
      }

      return rightTimestamp - leftTimestamp;
    });
  }, [articles, documents]);

  const publishedItemsCount = useMemo(
    () => libraryItems.filter((item) => item.status === "Published").length,
    [libraryItems]
  );

  const draftItemsCount = useMemo(
    () => libraryItems.filter((item) => item.status === "Draft").length,
    [libraryItems]
  );

  const visibleLibraryItems = useMemo(() => {
    const normalizedSearch = deferredSearch.trim().toLowerCase();

    if (!normalizedSearch) {
      return libraryItems;
    }

    return libraryItems.filter((item) => item.search_text.includes(normalizedSearch));
  }, [deferredSearch, libraryItems]);

  const privateTrainingItems = useMemo(
    () =>
      libraryItems.filter(
        (item) => item.item_kind === "guidance" || item.item_kind === "help-center-articles"
      ),
    [libraryItems]
  );

  const filesAndPagesItems = useMemo(
    () =>
      libraryItems.filter(
        (item) =>
          item.item_kind === "documents" ||
          item.item_kind === "store-website" ||
          item.item_kind === "urls"
      ),
    [libraryItems]
  );

  const livePrivateTrainingCount = useMemo(
    () => privateTrainingItems.filter((item) => item.status === "Published").length,
    [privateTrainingItems]
  );

  const liveFilesAndPagesCount = useMemo(
    () => filesAndPagesItems.filter((item) => item.status === "Published").length,
    [filesAndPagesItems]
  );

  function closeOverlay() {
    setOverlay("closed");
  }

  function resetUploadFlow() {
    setUploadDraft(emptyUploadDraft());
    setUploadFiles([]);
    setUploadInputVersion((current) => current + 1);
  }

  function openCreateGuidance(sourceType = "manual") {
    setDraft(emptyKnowledgeDraft(sourceType));
    setError("");
    setOverlay("manage-knowledge");
  }

  function openRulePicker() {
    setError("");
    setOverlay("pick-rules");
  }

  function openSourcePicker() {
    setError("");
    setOverlay("pick-sources");
  }

  function openCreateArticle() {
    setArticleDraft(emptyArticleDraft());
    setError("");
    setOverlay("manage-article");
  }

  function openUploadOverlay() {
    resetUploadFlow();
    setError("");
    setOverlay("upload");
  }

  function openWebsiteOverlay() {
    setWebsiteDraft(emptyWebsiteDraft());
    setError("");
    setOverlay("store-website");
  }

  function openUrlsOverlay() {
    setUrlImportDraft(emptyUrlImportDraft());
    setError("");
    setOverlay("urls");
  }

  useEffect(() => {
    const trainTarget = searchParams.get("train");

    if (!trainTarget) {
      return;
    }

    if (trainTarget === "rule") {
      openCreateGuidance("manual");
    } else if (trainTarget === "answer") {
      openCreateArticle();
    } else if (trainTarget === "website") {
      openWebsiteOverlay();
    } else if (trainTarget === "url") {
      openUrlsOverlay();
    } else if (trainTarget === "file") {
      openUploadOverlay();
    } else if (trainTarget === "test") {
      setError("");
      setOverlay("test");
    } else {
      return;
    }

    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.delete("train");
    setSearchParams(nextSearchParams, { replace: true });
  }, [searchParams, setSearchParams]);

  function openEditDocument(document: KnowledgeDocumentRecord) {
    setDraft(knowledgeDocumentToDraft(document));
    setError("");
    setOverlay("manage-knowledge");
  }

  function openEditArticle(article: SupportArticleRecord) {
    setArticleDraft(articleToDraft(article));
    setError("");
    setOverlay("manage-article");
  }

  function handleManageItem(item: LibraryItem) {
    if (item.record_kind === "article") {
      const matchedArticle = articles.find((article) => article.id === item.id);

      if (matchedArticle) {
        openEditArticle(matchedArticle);
      }

      return;
    }

    const matchedDocument = documents.find((document) => document.id === item.id);

    if (matchedDocument) {
      openEditDocument(matchedDocument);
    }
  }

  async function handleSaveDocument() {
    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");

      const payload = {
        body: draft.body,
        category: draft.category,
        source_name: draft.source_name,
        source_type: draft.source_type,
        status: draft.status,
        summary: draft.summary,
        tags: draft.tags,
        title: draft.title
      };

      if (draft.id) {
        await updateAdminKnowledgeDocument(draft.id, payload);
        setSuccessMessage("Team rule saved.");
      } else {
        await createAdminKnowledgeDocument(payload);
        setSuccessMessage("Team rule added.");
      }

      await loadLibraryContent();
      setOverlay("closed");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save the team rule.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveArticle() {
    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");

      const payload = {
        body: articleDraft.body,
        category: articleDraft.category,
        keywords: articleDraft.keywords,
        status: articleDraft.status,
        summary: articleDraft.summary,
        title: articleDraft.title,
        url: articleDraft.url
      };

      if (articleDraft.id) {
        await updateAdminArticle(articleDraft.id, payload);
        setSuccessMessage("Customer answer saved.");
      } else {
        await createAdminArticle(payload);
        setSuccessMessage("Customer answer added.");
      }

      await loadLibraryContent();
      setOverlay("closed");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save the customer answer.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveWebsiteKnowledge() {
    if (!websiteDraft.site_url.trim()) {
      setError("Add the store website URL before saving.");
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");

      const syncScope = websiteDraft.sync_scope.trim();
      const response = await importAdminKnowledgeUrl({
        body_note: [syncScope ? `Sync scope: ${syncScope}` : "", websiteDraft.body.trim()]
          .filter(Boolean)
          .join("\n\n"),
        category: websiteDraft.category,
        source_type: "store-website",
        status: websiteDraft.status,
        summary: websiteDraft.summary.trim(),
        tags: websiteDraft.tags,
        title_prefix: websiteDraft.site_name.trim(),
        url: websiteDraft.site_url.trim()
      });
      await loadLibraryContent();
      setOverlay("closed");
      setSuccessMessage(`Website indexed: ${response.documents.length} knowledge section${response.documents.length === 1 ? "" : "s"} added.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save the website info.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveUrlsKnowledge() {
    const parsedUrls = urlImportDraft.urls_text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    if (!parsedUrls.length) {
      setError("Add at least one URL before importing.");
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");

      const responses = await Promise.all(
        parsedUrls.map((rawUrl) =>
          importAdminKnowledgeUrl({
            body_note: urlImportDraft.body.trim(),
            category: urlImportDraft.category,
            status: urlImportDraft.status,
            summary: urlImportDraft.summary.trim(),
            tags: urlImportDraft.tags,
            title_prefix: urlImportDraft.title_prefix,
            url: rawUrl
          })
        )
      );
      const importedDocumentCount = responses.reduce(
        (total, response) => total + response.documents.length,
        0
      );
      const warningCount = responses.filter((response) => response.warning?.trim()).length;

      await loadLibraryContent();
      setOverlay("closed");
      setSuccessMessage(
        `Imported ${parsedUrls.length} link${parsedUrls.length === 1 ? "" : "s"} into ${importedDocumentCount} AI item${
          importedDocumentCount === 1 ? "" : "s"
        }.${warningCount ? ` ${warningCount} link${warningCount === 1 ? " was" : "s were"} split into smaller AI items.` : ""}`
      );
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not add the links.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleUploadDocuments() {
    if (!uploadFiles.length) {
      setError("Choose at least one training file before uploading.");
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");

      const files = await Promise.all(
        uploadFiles.map(async (file) => ({
          content_base64: await readFileAsDataUrl(file),
          mime_type: file.type,
          name: file.name
        }))
      );
      const response = await uploadAdminKnowledgeDocuments({
        category: uploadDraft.category,
        files,
        source_name: uploadDraft.source_name,
        status: uploadDraft.status,
        tags: uploadDraft.tags
      });
      const warningCount = response.files.filter((file) => file.warning?.trim()).length;

      await loadLibraryContent();
      resetUploadFlow();
      setOverlay("closed");
      setSuccessMessage(
        `Added ${response.documents.length} AI item${
          response.documents.length === 1 ? "" : "s"
        } from ${response.files.length} file${response.files.length === 1 ? "" : "s"}.${
          warningCount ? ` ${warningCount} file${warningCount === 1 ? " was" : "s were"} split into smaller AI items.` : ""
        }`
      );
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Could not upload the files.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleRunAssistTest() {
    if (!testIssue.trim()) {
      setError("Type a question before asking the AI.");
      return;
    }

    try {
      setIsTesting(true);
      setError("");
      setAssistResponse(
        await getSupportAssist({
          issue: testIssue.trim(),
          limit: 3
        })
      );
    } catch (assistError) {
      setError(assistError instanceof Error ? assistError.message : "Could not ask the AI.");
    } finally {
      setIsTesting(false);
    }
  }

  function renderLibraryCard(item: LibraryItem) {
    const itemKey = getLibraryItemKey(item);
    const sourceNamePreview = formatSourceNamePreview(item);

    return (
      <article className="knowledge-item-card" key={itemKey}>
        <div className="knowledge-item-head">
          <div className="knowledge-item-title-block">
            <span className={`knowledge-row-icon kind-${item.item_kind}`}>
              {getKnowledgeItemIconLabel(item)}
            </span>
            <div className="knowledge-item-title-copy">
              <strong>{item.title}</strong>
              <p>{item.summary || getItemTypeExplanation(item)}</p>
            </div>
          </div>

          <div className={`knowledge-item-status ${item.status === "Published" ? "live" : "draft"}`}>
            {getItemStatusLabel(item.status)}
          </div>
        </div>

        <div className="knowledge-item-helper">{getItemStatusDescription(item.status)}</div>

        <div className="knowledge-item-meta">
          <span className="knowledge-meta-pill">{item.source_label}</span>
          <span className="knowledge-meta-pill">{item.category || "General"}</span>
          {sourceNamePreview ? <span className="knowledge-meta-pill">{sourceNamePreview}</span> : null}
          {item.tags.slice(0, 3).map((tag) => (
            <span className="knowledge-meta-pill" key={`${itemKey}-${tag}`}>
              {tag}
            </span>
          ))}
        </div>

        <div className="knowledge-item-footer">
          <span>Updated {formatKnowledgeDate(item.updated_at)}</span>
          <button className="ghost-button" onClick={() => handleManageItem(item)} type="button">
            Edit
          </button>
        </div>
      </article>
    );
  }

  return (
    <div className="stack-page knowledge-library-page train-ui-page">
      <TrainHero
        actionLabel="Start with step 1"
        description="Add an answer, add a file, then test one question."
        eyebrow={embedded ? "Knowledge workspace" : "Train"}
        onAction={openRulePicker}
        stats={[
          {
            label: "Total items",
            note: "Everything added so far",
            value: libraryItems.length
          },
          {
            label: "Ready now",
            note: "AI can use these now",
            value: publishedItemsCount
          },
          {
            label: "Not ready",
            note: "Saved for later",
            value: draftItemsCount
          }
        ]}
        tip="Do only this order: answer first, file second, test third."
        title="Add answers and files"
      />

      {error ? <div className="banner-error">{error}</div> : null}
      {successMessage ? <div className="banner-success">{successMessage}</div> : null}

      <TrainSplitCallout
        actionLabel="Add answer or rule"
        description="Start here first."
        eyebrow="Best first click"
        onAction={openRulePicker}
        title="Start with answer or rule"
      />

      <section className="plain-card knowledge-library-shell">
        <div className="knowledge-library-topbar">
          <div>
            <div className="knowledge-library-kicker">Step By Step</div>
            <div className="section-title knowledge-library-title">Use the 3 boxes below</div>
            <div className="section-copy">
              Do one box at a time. You do not need to understand everything at once.
            </div>
          </div>
        </div>

        <section className="knowledge-focus-section">
          <div className="knowledge-focus-head">
            <div>
              <div className="knowledge-library-kicker">Step 1</div>
              <div className="section-title small">Add team rules and customer answers</div>
              <div className="section-copy">
                Put your team rules here. You can also add a ready answer the AI may say.
              </div>
            </div>

            <div className="knowledge-focus-metrics">
              <div className="knowledge-mini-stat">
                <strong>{privateTrainingItems.length}</strong>
                <span>total</span>
              </div>
              <div className="knowledge-mini-stat">
                <strong>{livePrivateTrainingCount}</strong>
                <span>ready</span>
              </div>
            </div>
          </div>

          <div className="knowledge-create-grid">
            <button className="knowledge-create-card" onClick={openCreateArticle} type="button">
              <strong>Add customer answer</strong>
              <span>The AI may say this to customers.</span>
            </button>

            <button className="knowledge-create-card" onClick={() => openCreateGuidance("manual")} type="button">
              <strong>Add team-only rule</strong>
              <span>Only your team sees this.</span>
            </button>
          </div>
          <div className="knowledge-step-note">
            {privateTrainingItems.length
              ? `${privateTrainingItems.length} rule${privateTrainingItems.length === 1 ? "" : "s"} or answer${privateTrainingItems.length === 1 ? "" : "s"} added`
              : "No rules yet"}
          </div>
        </section>

        <section className="knowledge-focus-section">
          <div className="knowledge-focus-head">
            <div>
              <div className="knowledge-library-kicker">Step 2</div>
              <div className="section-title small">Add files, links, or website info</div>
              <div className="section-copy">
                Add files, links, or website info so the AI has more to read.
              </div>
            </div>

            <div className="knowledge-focus-metrics">
              <div className="knowledge-mini-stat">
                <strong>{filesAndPagesItems.length}</strong>
                <span>total</span>
              </div>
              <div className="knowledge-mini-stat">
                <strong>{liveFilesAndPagesCount}</strong>
                <span>ready</span>
              </div>
            </div>
          </div>

          <div className="knowledge-create-grid knowledge-create-grid-triple">
            <button className="knowledge-create-card" onClick={openWebsiteOverlay} type="button">
              <strong>Add website</strong>
              <span>Use pages from your website.</span>
            </button>

            <button className="knowledge-create-card" onClick={openUrlsOverlay} type="button">
              <strong>Add one link</strong>
              <span>Use one page or one link.</span>
            </button>

            <button className="knowledge-create-card" onClick={openUploadOverlay} type="button">
              <strong>Add file</strong>
              <span>Use a PDF or document file.</span>
            </button>
          </div>
          <div className="knowledge-step-note">
            {filesAndPagesItems.length
              ? `${filesAndPagesItems.length} file${filesAndPagesItems.length === 1 ? "" : "s"} or link${filesAndPagesItems.length === 1 ? "" : "s"} added`
              : "No files or links yet"}
          </div>
        </section>

        <section className="knowledge-focus-section">
          <div className="knowledge-focus-head">
            <div>
              <div className="knowledge-library-kicker">Step 3</div>
              <div className="section-title small">Ask one customer question</div>
              <div className="section-copy">
                Type a customer question and see what the AI says.
              </div>
            </div>

            <div className="knowledge-focus-metrics">
              <div className="knowledge-mini-stat">
                <strong>{publishedItemsCount}</strong>
                <span>ready</span>
              </div>
              <div className="knowledge-mini-stat">
                <strong>{draftItemsCount}</strong>
                <span>not ready</span>
              </div>
            </div>
          </div>

          <div className="knowledge-test-shell">
            <label className="field-block">
              <span>Type a question</span>
              <textarea
                className="field-textarea short"
                onChange={(event) => setTestIssue(event.target.value)}
                placeholder="Example: My order arrived damaged. Can I get a replacement and how long will it take?"
                rows={4}
                value={testIssue}
              />
            </label>

            <button className="knowledge-step-button" disabled={isTesting} onClick={() => void handleRunAssistTest()} type="button">
              {isTesting ? "Checking..." : "Ask one question"}
            </button>

            {assistResponse ? (
              <div className="stack-page">
                <div className="preview-shell">{assistResponse.answer}</div>

                <div className="badge-row compact">
                  <span className="badge-chip dark">
                    {assistResponse.used_llm ? "AI answer" : "Basic answer"}
                  </span>
                  {assistResponse.confidence_label ? (
                    <span className="badge-chip dark">Confidence: {assistResponse.confidence_label}</span>
                  ) : null}
                  {assistResponse.handoff_recommended ? (
                    <span className="badge-chip dark">A person should help</span>
                  ) : null}
                </div>

                <div className="knowledge-item-grid">
                  {assistResponse.knowledge_documents.map((document) => (
                    <article className="knowledge-item-card" key={document.id}>
                      <div className="knowledge-item-head">
                        <div className="knowledge-item-title-block">
                          <span className="knowledge-row-icon kind-guidance">G</span>
                          <div className="knowledge-item-title-copy">
                            <strong>{document.title}</strong>
                            <p>{document.summary || "Matched team rule"}</p>
                          </div>
                        </div>
                      </div>
                    </article>
                  ))}

                  {assistResponse.articles.map((article) => (
                    <article className="knowledge-item-card" key={`${article.id}-${article.title}`}>
                      <div className="knowledge-item-head">
                        <div className="knowledge-item-title-block">
                          <span className="knowledge-row-icon kind-help-center-articles">A</span>
                          <div className="knowledge-item-title-copy">
                            <strong>{article.title}</strong>
                            <p>{article.summary || "Matched customer answer"}</p>
                          </div>
                        </div>
                      </div>
                    </article>
                  ))}

                  {!assistResponse.knowledge_documents.length && !assistResponse.articles.length ? (
                    <div className="empty-card knowledge-empty-state">
                      <strong>No ready item matched this answer.</strong>
                      <span>Try adding a better team rule, customer answer, file, or link for this question.</span>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <section className="knowledge-library-browser">
          <div className="knowledge-focus-head">
            <div>
              <div className="knowledge-library-kicker">What AI Knows</div>
              <div className="section-title small">Edit anything you already added</div>
              <div className="section-copy">
                Search below if you want to change a rule, answer, file, or link.
              </div>
            </div>
          </div>

          <div className="knowledge-search-banner">
            <input
              className="rail-search knowledge-search-input"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search what AI knows..."
              type="search"
              value={search}
            />
            <div className="knowledge-search-hint">
              {search
                ? `${visibleLibraryItems.length} matching item${visibleLibraryItems.length === 1 ? "" : "s"}`
                : `${libraryItems.length} total item${libraryItems.length === 1 ? "" : "s"}`}
            </div>
          </div>

          <div className="knowledge-item-grid">
            {visibleLibraryItems.map(renderLibraryCard)}

            {!visibleLibraryItems.length ? (
              <div className="empty-card knowledge-empty-state">
                <strong>Nothing matched your search.</strong>
                <span>Try a different word or clear the search.</span>
              </div>
            ) : null}
          </div>
        </section>
      </section>

      {overlay === "pick-rules" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">Step 1</div>
                <div className="section-title small">What do you want to add?</div>
                <div className="section-copy">Pick one simple option.</div>
              </div>

              <button className="knowledge-modal-close" onClick={closeOverlay} type="button">
                x
              </button>
            </div>

            <div className="knowledge-create-grid">
              <button className="knowledge-create-card" onClick={() => openCreateGuidance("manual")} type="button">
                <strong>Add team rule</strong>
                <span>Use this for private rules only your team sees.</span>
              </button>

              <button className="knowledge-create-card" onClick={openCreateArticle} type="button">
                <strong>Add customer answer</strong>
                <span>Use this for a ready answer the AI can say to customers.</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {overlay === "pick-sources" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">Step 2</div>
                <div className="section-title small">What do you want to add?</div>
                <div className="section-copy">Pick one simple option.</div>
              </div>

              <button className="knowledge-modal-close" onClick={closeOverlay} type="button">
                x
              </button>
            </div>

            <div className="knowledge-create-grid">
              <button className="knowledge-create-card" onClick={openUploadOverlay} type="button">
                <strong>Add file</strong>
                <span>Upload a file so the AI can learn from it.</span>
              </button>

              <button className="knowledge-create-card" onClick={openUrlsOverlay} type="button">
                <strong>Add link</strong>
                <span>Paste a link you want the AI to use.</span>
              </button>

              <button className="knowledge-create-card" onClick={openWebsiteOverlay} type="button">
                <strong>Add website info</strong>
                <span>Save website details the AI should remember.</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {overlay === "manage-knowledge" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell wide">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">Team Rule</div>
                <div className="section-title">{getKnowledgeEditorTitle(draft.source_type, draft.id)}</div>
                <div className="section-copy">
                  Only your team sees this. The AI uses it when writing replies.
                </div>
              </div>

              <div className="knowledge-modal-actions">
                <button className="ghost-button" onClick={closeOverlay} type="button">
                  Cancel
                </button>
                <button className="primary-button" disabled={isWorking} onClick={() => void handleSaveDocument()} type="button">
                  Save rule
                </button>
              </div>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Rule name</span>
                <input
                  className="field-input"
                  onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
                  placeholder="Damaged order replacement steps"
                  value={draft.title}
                />
              </label>

              <label className="field-block">
                <span>Topic</span>
                <input
                  className="field-input"
                  onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))}
                  placeholder="Logistics"
                  value={draft.category}
                />
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Use now?</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      status: event.target.value as KnowledgeDocumentRecord["status"]
                    }))
                  }
                  value={draft.status}
                >
                  <option value="Published">Yes - AI can use this now</option>
                  <option value="Draft">No - save for later</option>
                </select>
              </label>

              <label className="field-block">
                <span>Rule type</span>
                <select
                  className="field-input"
                  onChange={(event) => setDraft((current) => ({ ...current, source_type: event.target.value }))}
                  value={draft.source_type}
                >
                  <option value="manual">Team rule</option>
                  <option value="policy">Team rule</option>
                  <option value="playbook">Step-by-step rule</option>
                  <option value="store-website">Website info</option>
                  <option value="url">Link</option>
                  <option value="upload">File</option>
                </select>
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Where it came from</span>
                <input
                  className="field-input"
                  onChange={(event) => setDraft((current) => ({ ...current, source_name: event.target.value }))}
                  placeholder="Refund SOP, owner note, courier page"
                  value={draft.source_name}
                />
              </label>

              <label className="field-block">
                <span>Tags</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      tags: parseCommaSeparatedList(event.target.value)
                    }))
                  }
                  placeholder="refund, logistics, vip"
                  value={draft.tags.join(", ")}
                />
              </label>
            </div>

            <label className="field-block">
              <span>Short summary</span>
              <textarea
                className="field-textarea short"
                onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))}
                placeholder="Example: Orders damaged in transit should be replaced after photo proof is confirmed."
                rows={3}
                value={draft.summary}
              />
            </label>

            <label className="field-block">
              <span>What should AI do?</span>
              <textarea
                className="field-textarea tall"
                onChange={(event) => setDraft((current) => ({ ...current, body: event.target.value }))}
                placeholder="Write the rule in simple words. Tell the AI what to say, what not to say, and when a human should help."
                value={draft.body}
              />
            </label>

            <div className="plain-card inset knowledge-preview-card">
              <div className="section-title small">Preview</div>
              <div className="preview-shell">{knowledgePreviewCopy(draft)}</div>
              <div className="tag-cloud">
                <span className="badge-chip dark">{draft.category || "Knowledge"}</span>
                <span className="badge-chip dark">{formatSourceFilterLabel(draft.source_type)}</span>
                {draft.source_name ? <span className="badge-chip dark">{draft.source_name}</span> : null}
                {draft.tags.map((tag) => (
                  <span className="badge-chip dark" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {overlay === "manage-article" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell wide">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">Customer Answer</div>
                <div className="section-title">
                  {articleDraft.id ? "Edit customer answer" : "Add customer answer"}
                </div>
                <div className="section-copy">
                  Customers can see this answer. The AI can reuse it later.
                </div>
              </div>

              <div className="knowledge-modal-actions">
                <button className="ghost-button" onClick={closeOverlay} type="button">
                  Cancel
                </button>
                <button className="primary-button" disabled={isWorking} onClick={() => void handleSaveArticle()} type="button">
                  Save answer
                </button>
              </div>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Answer name</span>
                <input
                  className="field-input"
                  onChange={(event) => setArticleDraft((current) => ({ ...current, title: event.target.value }))}
                  placeholder="How refund timing works"
                  value={articleDraft.title}
                />
              </label>

              <label className="field-block">
                <span>Topic</span>
                <input
                  className="field-input"
                  onChange={(event) => setArticleDraft((current) => ({ ...current, category: event.target.value }))}
                  placeholder="Billing"
                  value={articleDraft.category}
                />
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Use now?</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setArticleDraft((current) => ({
                      ...current,
                      status: event.target.value as SupportArticleRecord["status"]
                    }))
                  }
                  value={articleDraft.status}
                >
                  <option value="Published">Yes - AI can use this now</option>
                  <option value="Draft">No - save for later</option>
                </select>
              </label>

              <label className="field-block">
                <span>Link for this answer</span>
                <input
                  className="field-input"
                  onChange={(event) => setArticleDraft((current) => ({ ...current, url: event.target.value }))}
                  placeholder="https://support.example.com/article"
                  value={articleDraft.url}
                />
              </label>
            </div>

            <label className="field-block">
              <span>Short summary</span>
              <textarea
                className="field-textarea short"
                onChange={(event) => setArticleDraft((current) => ({ ...current, summary: event.target.value }))}
                placeholder="Example: Refunds usually appear within 5 to 10 business days depending on the bank."
                rows={3}
                value={articleDraft.summary}
              />
            </label>

            <label className="field-block">
              <span>Keywords</span>
              <input
                className="field-input"
                onChange={(event) =>
                  setArticleDraft((current) => ({
                    ...current,
                    keywords: parseCommaSeparatedList(event.target.value)
                  }))
                }
                placeholder="refund, delivery, subscription"
                value={articleDraft.keywords.join(", ")}
              />
            </label>

            <label className="field-block">
              <span>What should the customer read?</span>
              <textarea
                className="field-textarea tall"
                onChange={(event) => setArticleDraft((current) => ({ ...current, body: event.target.value }))}
                placeholder="Write the final answer you want customers to receive."
                value={articleDraft.body}
              />
            </label>

            <div className="plain-card inset knowledge-preview-card">
              <div className="section-title small">Preview</div>
              <div className="preview-shell">{articlePreviewCopy(articleDraft)}</div>
              <div className="tag-cloud">
                <span className="badge-chip dark">{articleDraft.category || "Support"}</span>
                {articleDraft.url ? <span className="badge-chip dark">{articleDraft.url}</span> : null}
                {articleDraft.keywords.map((keyword) => (
                  <span className="badge-chip dark" key={keyword}>
                    {keyword}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {overlay === "store-website" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell wide">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">Website Info</div>
                <div className="section-title">Add website info</div>
                <div className="section-copy">
                  Put website details here so the AI can remember them.
                </div>
              </div>

              <div className="knowledge-modal-actions">
                <button className="ghost-button" onClick={closeOverlay} type="button">
                  Cancel
                </button>
                <button className="primary-button" disabled={isWorking} onClick={() => void handleSaveWebsiteKnowledge()} type="button">
                  Save website info
                </button>
              </div>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Store name</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setWebsiteDraft((current) => ({
                      ...current,
                      site_name: event.target.value
                    }))
                  }
                  placeholder="macro-store1"
                  value={websiteDraft.site_name}
                />
              </label>

              <label className="field-block">
                <span>Website link</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setWebsiteDraft((current) => ({
                      ...current,
                      site_url: event.target.value
                    }))
                  }
                  placeholder="https://store.example.com"
                  value={websiteDraft.site_url}
                />
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Use now?</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setWebsiteDraft((current) => ({
                      ...current,
                      status: event.target.value as KnowledgeDocumentRecord["status"]
                    }))
                  }
                  value={websiteDraft.status}
                >
                  <option value="Published">Yes - AI can use this now</option>
                  <option value="Draft">No - save for later</option>
                </select>
              </label>

              <label className="field-block">
                <span>Topic</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setWebsiteDraft((current) => ({
                      ...current,
                      category: event.target.value
                    }))
                  }
                  placeholder="Website"
                  value={websiteDraft.category}
                />
              </label>
            </div>

            <label className="field-block">
              <span>Which pages matter?</span>
              <textarea
                className="field-textarea short"
                onChange={(event) =>
                  setWebsiteDraft((current) => ({
                    ...current,
                    sync_scope: event.target.value
                  }))
                }
                placeholder="Example: Product pages, FAQ, shipping policies, returns, and meal plan pages."
                rows={3}
                value={websiteDraft.sync_scope}
              />
            </label>

            <label className="field-block">
              <span>Short summary</span>
              <textarea
                className="field-textarea short"
                onChange={(event) =>
                  setWebsiteDraft((current) => ({
                    ...current,
                    summary: event.target.value
                  }))
                }
                placeholder="Example: Shipping, returns, and meal plan pages are the main website sources for support answers."
                rows={3}
                value={websiteDraft.summary}
              />
            </label>

            <label className="field-block">
              <span>What should AI remember?</span>
              <textarea
                className="field-textarea tall"
                onChange={(event) =>
                  setWebsiteDraft((current) => ({
                    ...current,
                    body: event.target.value
                  }))
                }
                placeholder="Write the website details the AI should remember."
                value={websiteDraft.body}
              />
            </label>

            <label className="field-block">
              <span>Tags</span>
              <input
                className="field-input"
                onChange={(event) =>
                  setWebsiteDraft((current) => ({
                    ...current,
                    tags: parseCommaSeparatedList(event.target.value)
                  }))
                }
                placeholder="website, storefront, faq"
                value={websiteDraft.tags.join(", ")}
              />
            </label>
          </div>
        </div>
      ) : null}

      {overlay === "urls" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell wide">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">Link</div>
                <div className="section-title">Add link</div>
                <div className="section-copy">
                  Paste one or more links and tell the AI why they matter.
                </div>
              </div>

              <div className="knowledge-modal-actions">
                <button className="ghost-button" onClick={closeOverlay} type="button">
                  Cancel
                </button>
                <button className="primary-button" disabled={isWorking} onClick={() => void handleSaveUrlsKnowledge()} type="button">
                  Import link
                </button>
              </div>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Short name</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setUrlImportDraft((current) => ({
                      ...current,
                      title_prefix: event.target.value
                    }))
                  }
                  placeholder="Support page"
                  value={urlImportDraft.title_prefix}
                />
              </label>

              <label className="field-block">
                <span>Topic</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setUrlImportDraft((current) => ({
                      ...current,
                      category: event.target.value
                    }))
                  }
                  placeholder="Delivery"
                  value={urlImportDraft.category}
                />
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Use now?</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setUrlImportDraft((current) => ({
                      ...current,
                      status: event.target.value as KnowledgeDocumentRecord["status"]
                    }))
                  }
                  value={urlImportDraft.status}
                >
                  <option value="Published">Yes - AI can use this now</option>
                  <option value="Draft">No - save for later</option>
                </select>
              </label>

              <label className="field-block">
                <span>Tags</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setUrlImportDraft((current) => ({
                      ...current,
                      tags: parseCommaSeparatedList(event.target.value)
                    }))
                  }
                  placeholder="tracking, faq, delivery"
                  value={urlImportDraft.tags.join(", ")}
                />
              </label>
            </div>

            <label className="field-block">
              <span>Link</span>
              <textarea
                className="field-textarea short"
                onChange={(event) =>
                  setUrlImportDraft((current) => ({
                    ...current,
                    urls_text: event.target.value
                  }))
                }
                placeholder={"Add one link per line.\nhttps://support.example.com/shipping\nhttps://support.example.com/refunds"}
                rows={5}
                value={urlImportDraft.urls_text}
              />
            </label>

            <label className="field-block">
              <span>Short summary</span>
              <textarea
                className="field-textarea short"
                onChange={(event) =>
                  setUrlImportDraft((current) => ({
                    ...current,
                    summary: event.target.value
                  }))
                }
                placeholder="Example: These pages explain delivery windows and refund rules."
                rows={3}
                value={urlImportDraft.summary}
              />
            </label>

            <label className="field-block">
              <span>Why should AI use this?</span>
              <textarea
                className="field-textarea tall"
                onChange={(event) =>
                  setUrlImportDraft((current) => ({
                    ...current,
                    body: event.target.value
                  }))
                }
                placeholder="Write a simple note about this link."
                value={urlImportDraft.body}
              />
            </label>
          </div>
        </div>
      ) : null}

      {overlay === "upload" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell wide">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">File</div>
                <div className="section-title">Add file</div>
                <div className="section-copy">
                  Upload a file so the AI can learn from it.
                </div>
              </div>

              <div className="knowledge-modal-actions">
                <button className="ghost-button" onClick={closeOverlay} type="button">
                  Cancel
                </button>
                <button className="primary-button" disabled={isWorking || !uploadFiles.length} onClick={() => void handleUploadDocuments()} type="button">
                  Save file
                </button>
              </div>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Topic</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setUploadDraft((current) => ({
                      ...current,
                      category: event.target.value
                    }))
                  }
                  placeholder="Operations"
                  value={uploadDraft.category}
                />
              </label>

              <label className="field-block">
                <span>Use now?</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setUploadDraft((current) => ({
                      ...current,
                      status: event.target.value as KnowledgeDocumentRecord["status"]
                    }))
                  }
                  value={uploadDraft.status}
                >
                  <option value="Published">Yes - AI can use this now</option>
                  <option value="Draft">No - save for later</option>
                </select>
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>File name for AI</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setUploadDraft((current) => ({
                      ...current,
                      source_name: event.target.value
                    }))
                  }
                  placeholder="Warehouse SOP batch, delivery FAQ, owner briefing"
                  value={uploadDraft.source_name}
                />
              </label>

              <label className="field-block">
                <span>Tags</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setUploadDraft((current) => ({
                      ...current,
                      tags: parseCommaSeparatedList(event.target.value)
                    }))
                  }
                  placeholder="refund, shipping, policy"
                  value={uploadDraft.tags.join(", ")}
                />
              </label>
            </div>

            <label className="support-upload-pill knowledge-upload-pill">
              <strong>Pick file</strong>
              <small>Short files are easier for the AI to learn from.</small>
              <input
                accept=".txt,.md,.markdown,.csv,.json,.htm,.html,.docx,.pdf"
                key={uploadInputVersion}
                multiple
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setUploadFiles(Array.from(event.target.files ?? []))
                }
                type="file"
              />
            </label>

            <div className="workspace-directory-grid">
              {uploadFiles.map((file) => (
                <article className="workspace-record-card article-record-card" key={`${file.name}-${file.lastModified}`}>
                  <div className="workspace-record-icon">F</div>
                  <div className="workspace-record-main">
                    <div className="workspace-record-title-row">
                      <strong>{file.name}</strong>
                    </div>
                    <div className="workspace-record-copy">
                      {file.type || "Unknown file type"} / {(file.size / 1024).toFixed(1)} KB
                    </div>
                  </div>
                </article>
              ))}

              {!uploadFiles.length ? (
                <div className="empty-card">No file picked yet.</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {overlay === "test" ? (
        <div aria-modal="true" className="knowledge-modal-backdrop" role="dialog">
          <div className="knowledge-modal-shell wide">
            <div className="knowledge-modal-head">
              <div>
                <div className="knowledge-library-kicker">Ask AI</div>
                <div className="section-title">Ask AI a question</div>
                <div className="section-copy">
                  Type a question. You will see the answer and what the AI used.
                </div>
              </div>

              <div className="knowledge-modal-actions">
                <button className="ghost-button" onClick={closeOverlay} type="button">
                  Close
                </button>
                <button className="primary-button" disabled={isTesting} onClick={() => void handleRunAssistTest()} type="button">
                  {isTesting ? "Checking..." : "Ask AI"}
                </button>
              </div>
            </div>

            <label className="field-block">
              <span>Type a question</span>
              <textarea
                className="field-textarea short"
                onChange={(event) => setTestIssue(event.target.value)}
                placeholder="Example: My order arrived damaged. Can I get a replacement and how long will it take?"
                rows={4}
                value={testIssue}
              />
            </label>

            {assistResponse ? (
              <div className="stack-page">
                <div className="preview-shell">{assistResponse.answer}</div>

                <div className="badge-row compact">
                  <span className="badge-chip dark">
                    {assistResponse.used_llm ? "AI answer" : "Basic answer"}
                  </span>
                  {assistResponse.confidence_label ? (
                    <span className="badge-chip dark">Confidence: {assistResponse.confidence_label}</span>
                  ) : null}
                  {assistResponse.handoff_recommended ? (
                    <span className="badge-chip dark">A person should help</span>
                  ) : null}
                </div>

                <div className="workspace-directory-grid">
                  {assistResponse.knowledge_documents.map((document) => (
                    <article className="workspace-record-card article-record-card" key={document.id}>
                      <div className="workspace-record-icon">G</div>
                      <div className="workspace-record-main">
                        <div className="workspace-record-title-row">
                          <strong>{document.title}</strong>
                        </div>
                        <div className="workspace-record-copy">
                          {document.summary || "Matched team rule"}
                        </div>
                      </div>
                    </article>
                  ))}

                  {assistResponse.articles.map((article) => (
                    <article className="workspace-record-card article-record-card" key={`${article.id}-${article.title}`}>
                      <div className="workspace-record-icon">A</div>
                      <div className="workspace-record-main">
                        <div className="workspace-record-title-row">
                          <strong>{article.title}</strong>
                        </div>
                        <div className="workspace-record-copy">
                          {article.summary || "Matched customer answer"}
                        </div>
                      </div>
                    </article>
                  ))}

                  {!assistResponse.knowledge_documents.length && !assistResponse.articles.length ? (
                    <div className="empty-card">The AI answered, but it did not use any ready item.</div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
