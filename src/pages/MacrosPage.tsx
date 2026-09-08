import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  archiveAdminMacro,
  createAdminMacro,
  deleteAdminMacro,
  duplicateAdminMacro,
  getAdminMacros,
  getAdminTags,
  updateAdminMacro
} from "../lib/api";
import type { Macro, TicketTag } from "../types";

type MacroDraft = {
  category: string;
  description: string;
  id: number | null;
  is_archived: number;
  language: string;
  name: string;
  response_text: string;
  set_status: string;
  subject_template: string;
  tag_names: string[];
};

type MacrosPageProps = {
  embedded?: boolean;
};

const categoryOptions = [
  "Billing",
  "Account",
  "Logistics",
  "NDIS",
  "Order",
  "General"
];

const languageOptions = ["English", "Auto detect", "Hindi", "Spanish"];

const statusOptions = [
  "",
  "Open",
  "In Progress",
  "Waiting on Customer",
  "Resolved",
  "Closed"
];

const previewVariables: Record<string, string> = {
  "{{ agent_first_name }}": "Sarah",
  "{{ assigned_agent }}": "Agent Sarah",
  "{{ brand_tag }}": "Acrobuild",
  "{{ customer_email }}": "jamie@example.com",
  "{{ customer_first_name }}": "Jamie",
  "{{ customer_name }}": "Jamie Taylor",
  "{{ intent_tag }}": "Delivery Delay",
  "{{ issue_type }}": "Logistics",
  "{{ priority }}": "High",
  "{{ queue_name }}": "Logistics Desk",
  "{{ status }}": "In Progress",
  "{{ ticket_id }}": "TK000321"
};

function emptyMacroDraft(): MacroDraft {
  return {
    category: "",
    description: "",
    id: null,
    is_archived: 0,
    language: "English",
    name: "New macro",
    response_text: "",
    set_status: "",
    subject_template: "",
    tag_names: []
  };
}

function macroToDraft(macro: Macro): MacroDraft {
  return {
    category: macro.category || "",
    description: macro.description || "",
    id: macro.id,
    is_archived: Number(macro.is_archived || 0),
    language: macro.language || "English",
    name: macro.name,
    response_text: macro.response_text || "",
    set_status: macro.set_status || "",
    subject_template: macro.subject_template || "",
    tag_names: [...(macro.tag_names || [])]
  };
}

function renderPreview(template: string) {
  return Object.entries(previewVariables).reduce(
    (currentText, [token, value]) => currentText.split(token).join(value),
    template
  );
}

function parseTagInput(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function describeMacro(macro: Macro) {
  return macro.subject_template || macro.description || macro.category || "Reusable support reply";
}

export function MacrosPage({ embedded = false }: MacrosPageProps) {
  const [macros, setMacros] = useState<Macro[]>([]);
  const [tags, setTags] = useState<TicketTag[]>([]);
  const [search, setSearch] = useState("");
  const [languageFilter, setLanguageFilter] = useState("All");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [view, setView] = useState<"Active" | "Archived">("Active");
  const [selectedMacroId, setSelectedMacroId] = useState<number | null>(null);
  const [draft, setDraft] = useState<MacroDraft>(emptyMacroDraft());
  const [extraTags, setExtraTags] = useState("");
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState("");
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const deferredSearch = useDeferredValue(search);

  async function loadMacros() {
    const response = await getAdminMacros({
      category: categoryFilter !== "All" ? categoryFilter : undefined,
      includeArchived: true,
      language: languageFilter !== "All" ? languageFilter : undefined,
      searchTerm: deferredSearch
    });

    setMacros(response.macros);
  }

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setError("");
        const [macroResponse, tagResponse] = await Promise.all([
          getAdminMacros({
            category: categoryFilter !== "All" ? categoryFilter : undefined,
            includeArchived: true,
            language: languageFilter !== "All" ? languageFilter : undefined,
            searchTerm: deferredSearch
          }),
          getAdminTags()
        ]);

        if (cancelled) {
          return;
        }

        setMacros(macroResponse.macros);
        setTags(tagResponse.tags);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load macros.");
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, [categoryFilter, deferredSearch, languageFilter]);

  useEffect(() => {
    if (selectedMacroId === null) {
      return;
    }

    const selectedMacro = macros.find((macro) => macro.id === selectedMacroId);

    if (selectedMacro) {
      setDraft(macroToDraft(selectedMacro));
      setExtraTags("");
    }
  }, [macros, selectedMacroId]);

  const visibleMacros = useMemo(
    () =>
      macros.filter((macro) =>
        view === "Archived"
          ? Boolean(Number(macro.is_archived || 0))
          : !Boolean(Number(macro.is_archived || 0))
      ),
    [macros, view]
  );

  const tagOptions = useMemo(() => {
    const knownTags = tags.map((tag) => tag.name);
    const combined = new Set([...knownTags, ...draft.tag_names]);
    return [...combined].sort((left, right) => left.localeCompare(right));
  }, [draft.tag_names, tags]);

  async function refreshAfterMutation(preferredMacroId?: number | null) {
    await loadMacros();

    if (preferredMacroId === null) {
      setSelectedMacroId(null);
      setDraft(emptyMacroDraft());
      setExtraTags("");
      setIsEditorOpen(false);
      return;
    }

    if (preferredMacroId) {
      setSelectedMacroId(preferredMacroId);
      setIsEditorOpen(true);
    }
  }

  async function handleSaveMacro() {
    try {
      setIsWorking(true);
      setError("");

      const payload = {
        category: draft.category,
        description: draft.description,
        language: draft.language,
        name: draft.name,
        response_text: draft.response_text,
        set_status: draft.set_status,
        subject_template: draft.subject_template,
        tag_names: [...new Set([...draft.tag_names, ...parseTagInput(extraTags)])]
      };

      if (draft.id) {
        const response = await updateAdminMacro(draft.id, payload);
        await refreshAfterMutation(response.macro.id);
      } else {
        const response = await createAdminMacro(payload);
        await refreshAfterMutation(response.macro.id);
      }
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save macro.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleDuplicateMacro() {
    if (!draft.id) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      const response = await duplicateAdminMacro(draft.id);
      await refreshAfterMutation(response.macro.id);
    } catch (duplicateError) {
      setError(duplicateError instanceof Error ? duplicateError.message : "Unable to duplicate macro.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleArchiveToggle() {
    if (!draft.id) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      await archiveAdminMacro(draft.id, !Boolean(draft.is_archived));
      await refreshAfterMutation(draft.id);
    } catch (archiveError) {
      setError(archiveError instanceof Error ? archiveError.message : "Unable to update archive state.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleDeleteMacro() {
    if (!draft.id) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      await deleteAdminMacro(draft.id);
      await refreshAfterMutation(null);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete macro.");
    } finally {
      setIsWorking(false);
    }
  }

  function toggleDraftTag(tagName: string) {
    setDraft((current) => ({
      ...current,
      tag_names: current.tag_names.includes(tagName)
        ? current.tag_names.filter((tag) => tag !== tagName)
        : [...current.tag_names, tagName]
    }));
  }

  function openCreateMacro() {
    setSelectedMacroId(null);
    setDraft(emptyMacroDraft());
    setExtraTags("");
    setIsEditorOpen(true);
  }

  function openEditMacro(macro: Macro) {
    setSelectedMacroId(macro.id);
    setDraft(macroToDraft(macro));
    setExtraTags("");
    setIsEditorOpen(true);
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Tools</div>
          <h2>Macros</h2>
          <p>Save polished reply templates, keep categories organized, and manage support copy without clutter.</p>
        </section>
      ) : null}

      {error ? <div className="banner-error">{error}</div> : null}

      {!isEditorOpen ? (
        <section className="plain-card workspace-directory-shell">
          <div className="workspace-directory-header">
            <div>
              <div className="section-title">Macro Library</div>
              <div className="section-copy">{visibleMacros.length} macros ready for the inbox</div>
            </div>

            <button className="primary-button management-plus-button" onClick={openCreateMacro} type="button">
              <span>+</span>
              New macro
            </button>
          </div>

          <div className="filter-grid">
            <input
              className="field-input"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search macros by name or category"
              value={search}
            />

            <select
              className="field-input"
              onChange={(event) => setLanguageFilter(event.target.value)}
              value={languageFilter}
            >
              <option value="All">All languages</option>
              {languageOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>

            <select
              className="field-input"
              onChange={(event) => setCategoryFilter(event.target.value)}
              value={categoryFilter}
            >
              <option value="All">All categories</option>
              {categoryOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>

            <select
              className="field-input"
              onChange={(event) => setView(event.target.value as "Active" | "Archived")}
              value={view}
            >
              <option value="Active">Active</option>
              <option value="Archived">Archived</option>
            </select>
          </div>

          <div className="workspace-directory-grid">
            {visibleMacros.map((macro) => (
              <article className="workspace-record-card" key={macro.id}>
                <div className="workspace-record-icon">M</div>
                <div className="workspace-record-main">
                  <div className="workspace-record-title-row">
                    <strong>{macro.name}</strong>
                  </div>
                  <div className="workspace-record-copy">{describeMacro(macro)}</div>
                  <div className="badge-row compact workspace-record-tag-row">
                    {(macro.tag_names || []).slice(0, 3).map((tagName) => (
                      <span className="badge-chip dark" key={tagName}>
                        <span className="badge-dot" style={{ backgroundColor: "#38bdf8" }} />
                        {tagName}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="workspace-record-meta macro-record-meta">
                  <span className="schedule-pill macro-record-status">
                    {Number(macro.is_archived || 0) ? "Archived" : "Active"}
                  </span>
                  <button
                    className="ghost-button small workspace-record-manage macro-record-manage"
                    onClick={() => openEditMacro(macro)}
                    type="button"
                  >
                    Manage
                  </button>
                </div>
              </article>
            ))}

            {!visibleMacros.length ? <div className="empty-card">No macros matched the current filters.</div> : null}
          </div>
        </section>
      ) : (
        <div className="workspace-detail-shell">
          <section className="plain-card">
            <div className="workspace-detail-topbar">
              <div>
                <div className="workspace-detail-kicker">Macro workspace</div>
                <div className="section-title">{draft.id ? "Manage macro" : "Create macro"}</div>
                <div className="section-copy">Keep the macro clean, tagged, and ready for the inbox composer.</div>
              </div>

              <div className="workspace-detail-actions">
                <button className="ghost-button" onClick={() => setIsEditorOpen(false)} type="button">
                  Back to library
                </button>
                <button
                  className="primary-button"
                  disabled={isWorking || !draft.name.trim() || !draft.response_text.trim()}
                  onClick={() => void handleSaveMacro()}
                  type="button"
                >
                  Save macro
                </button>
              </div>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Macro name</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      name: event.target.value
                    }))
                  }
                  value={draft.name}
                />
              </label>

              <label className="field-block">
                <span>Language</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      language: event.target.value
                    }))
                  }
                  value={draft.language}
                >
                  {languageOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="field-block">
              <span>Response template</span>
              <textarea
                className="field-textarea tall"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    response_text: event.target.value
                  }))
                }
                rows={12}
                value={draft.response_text}
              />
            </label>

            <div className="editor-grid">
              <label className="field-block">
                <span>Category</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      category: event.target.value
                    }))
                  }
                  value={draft.category}
                >
                  <option value="">No specific category</option>
                  {categoryOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-block">
                <span>Set status when sent</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      set_status: event.target.value
                    }))
                  }
                  value={draft.set_status}
                >
                  <option value="">No automatic status change</option>
                  {statusOptions
                    .filter((option) => option)
                    .map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                </select>
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Reply subject</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      subject_template: event.target.value
                    }))
                  }
                  value={draft.subject_template}
                />
              </label>

              <label className="field-block">
                <span>Internal description</span>
                <input
                  className="field-input"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      description: event.target.value
                    }))
                  }
                  value={draft.description}
                />
              </label>
            </div>

            <div className="field-block">
              <span>Quick tag picks</span>
              <div className="tag-cloud">
                {tagOptions.map((tagName) => (
                  <button
                    className={`tag-toggle${draft.tag_names.includes(tagName) ? " active" : ""}`}
                    key={tagName}
                    onClick={() => toggleDraftTag(tagName)}
                    type="button"
                  >
                    {tagName}
                  </button>
                ))}
              </div>
            </div>

            <label className="field-block">
              <span>Extra tags</span>
              <input
                className="field-input"
                onChange={(event) => setExtraTags(event.target.value)}
                placeholder="Add more tags separated by commas"
                value={extraTags}
              />
            </label>

            <div className="workspace-detail-preview">
              <div className="section-title small">Preview</div>
              <div className="preview-shell">
                {renderPreview(draft.response_text) || "Preview updates as you write the macro."}
              </div>
            </div>

            <div className="action-row wrap">
              <button
                className="ghost-button"
                disabled={isWorking || !draft.id}
                onClick={() => void handleDuplicateMacro()}
                type="button"
              >
                Duplicate
              </button>
              <button
                className="ghost-button"
                disabled={isWorking || !draft.id}
                onClick={() => void handleArchiveToggle()}
                type="button"
              >
                {draft.is_archived ? "Unarchive" : "Archive"}
              </button>
              <button
                className="mini-danger"
                disabled={isWorking || !draft.id}
                onClick={() => void handleDeleteMacro()}
                type="button"
              >
                Delete
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
