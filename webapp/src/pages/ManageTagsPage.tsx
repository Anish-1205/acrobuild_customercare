import { useDeferredValue, useEffect, useState } from "react";
import {
  createAdminTag,
  deleteAdminTag,
  getAdminTags,
  updateAdminTag
} from "../lib/api";
import type { TicketTag } from "../types";

type TagDraft = {
  color: string;
  description: string;
  name: string;
};

type ManageTagsPageProps = {
  embedded?: boolean;
};

const defaultDraft: TagDraft = {
  color: "#38bdf8",
  description: "",
  name: ""
};

function tagToDraft(tag: TicketTag): TagDraft {
  return {
    color: tag.color || "#38bdf8",
    description: tag.description || "",
    name: tag.name
  };
}

export function ManageTagsPage({ embedded = false }: ManageTagsPageProps) {
  const [tags, setTags] = useState<TicketTag[]>([]);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<TagDraft>(defaultDraft);
  const [editingTagId, setEditingTagId] = useState<number | null>(null);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState("");
  const [surface, setSurface] = useState<"list" | "create" | "edit">("list");
  const deferredSearch = useDeferredValue(search);

  async function loadTags(searchTerm = "") {
    const response = await getAdminTags(searchTerm);
    setTags(response.tags);
  }

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setError("");
        const response = await getAdminTags(deferredSearch);

        if (!cancelled) {
          setTags(response.tags);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load tags.");
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, [deferredSearch]);

  function openCreateTag() {
    setDraft(defaultDraft);
    setEditingTagId(null);
    setSurface("create");
  }

  function openEditTag(tag: TicketTag) {
    setEditingTagId(tag.id);
    setDraft(tagToDraft(tag));
    setSurface("edit");
  }

  async function handleCreateTag() {
    try {
      setIsWorking(true);
      setError("");
      await createAdminTag(draft);
      setDraft(defaultDraft);
      setSurface("list");
      await loadTags(deferredSearch);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to create tag.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSaveEdit() {
    if (!editingTagId) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      await updateAdminTag(editingTagId, draft);
      setSurface("list");
      await loadTags(deferredSearch);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to update tag.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleDeleteTag(tagId: number) {
    try {
      setIsWorking(true);
      setError("");
      await deleteAdminTag(tagId);

      if (editingTagId === tagId) {
        setEditingTagId(null);
        setDraft(defaultDraft);
        setSurface("list");
      }

      await loadTags(deferredSearch);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete tag.");
    } finally {
      setIsWorking(false);
    }
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Fields And Tags</div>
          <h2>Manage Tags</h2>
          <p>Keep routing labels tidy, reusable, and easy to manage from one clean tag directory.</p>
        </section>
      ) : null}

      {error ? <div className="banner-error">{error}</div> : null}

      {surface === "list" ? (
        <section className="plain-card workspace-directory-shell">
          <div className="workspace-directory-header">
            <div>
              <div className="section-title">Tag Library</div>
              <div className="section-copy">{tags.length} tags available for routing and organization</div>
            </div>

            <button className="primary-button management-plus-button" onClick={openCreateTag} type="button">
              <span>+</span>
              New tag
            </button>
          </div>

          <div className="toolbar-row wrap">
            <input
              className="rail-search wide"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search tags by name or description"
              value={search}
            />
          </div>

          <div className="workspace-directory-grid">
            {tags.map((tag) => (
              <article className="workspace-record-card" key={tag.id}>
                <div className="workspace-record-icon workspace-record-icon-tag" style={{ color: tag.color || "#38bdf8" }}>
                  #
                </div>
                <div className="workspace-record-main">
                  <div className="workspace-record-title-row">
                    <strong>{tag.name}</strong>
                  </div>
                  <div className="workspace-record-copy">{tag.description || "No description added yet."}</div>
                </div>
                <div className="workspace-record-meta tag-record-meta">
                  <span className="badge-chip dark tag-record-count">
                    <span className="badge-dot" style={{ backgroundColor: tag.color || "#38bdf8" }} />
                    {(tag.ticket_count ?? 0).toString()} tickets
                  </span>
                  <button
                    className="ghost-button small workspace-record-manage tag-record-manage"
                    onClick={() => openEditTag(tag)}
                    type="button"
                  >
                    Manage
                  </button>
                  <button
                    className="mini-danger small tag-record-delete"
                    disabled={isWorking}
                    onClick={() => void handleDeleteTag(tag.id)}
                    type="button"
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}

            {!tags.length ? <div className="empty-card">No tags matched the current search.</div> : null}
          </div>
        </section>
      ) : (
        <section className="plain-card workspace-detail-shell">
          <div className="workspace-detail-topbar">
            <div>
              <div className="workspace-detail-kicker">Tag workspace</div>
              <div className="section-title">{surface === "create" ? "Create tag" : "Manage tag"}</div>
              <div className="section-copy">Define the label, color, and description used across ticket routing.</div>
            </div>

            <div className="workspace-detail-actions">
              <button className="ghost-button" onClick={() => setSurface("list")} type="button">
                Back to library
              </button>
              <button
                className="primary-button"
                disabled={isWorking || !draft.name.trim()}
                onClick={() => void (surface === "create" ? handleCreateTag() : handleSaveEdit())}
                type="button"
              >
                {surface === "create" ? "Create tag" : "Save tag"}
              </button>
            </div>
          </div>

          <div className="editor-grid">
            <label className="field-block">
              <span>Tag name</span>
              <input
                className="field-input"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    name: event.target.value
                  }))
                }
                placeholder="during-business-hours"
                value={draft.name}
              />
            </label>

            <label className="field-block">
              <span>Color</span>
              <input
                className="color-input"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    color: event.target.value
                  }))
                }
                type="color"
                value={draft.color}
              />
            </label>
          </div>

          <label className="field-block">
            <span>Description</span>
            <textarea
              className="field-textarea short"
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  description: event.target.value
                }))
              }
              rows={5}
              value={draft.description}
            />
          </label>

          <div className="workspace-detail-preview">
            <div className="section-title small">Preview</div>
            <div className="workspace-tag-preview">
              <span className="badge-chip dark">
                <span className="badge-dot" style={{ backgroundColor: draft.color || "#38bdf8" }} />
                {draft.name || "new-tag"}
              </span>
              <p className="workspace-tag-preview-copy">
                {draft.description || "This tag will appear in routing, ticket badges, and filters."}
              </p>
            </div>
          </div>

          {surface === "edit" && editingTagId ? (
            <div className="action-row">
              <button
                className="mini-danger"
                disabled={isWorking}
                onClick={() => void handleDeleteTag(editingTagId)}
                type="button"
              >
                Delete tag
              </button>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}
