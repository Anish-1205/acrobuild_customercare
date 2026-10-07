import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AIAgentPage } from "./AIAgentPage";
import { ArticlesPage } from "./ArticlesPage";

const api = vi.hoisted(() => ({
  createAdminArticle: vi.fn(),
  createAdminKnowledgeDocument: vi.fn(),
  deleteAdminKnowledgeDocuments: vi.fn(),
  getAdminArticles: vi.fn(),
  getAdminKnowledgeDocuments: vi.fn(),
  getSupportAssist: vi.fn(),
  importAdminKnowledgeUrl: vi.fn(),
  updateAdminArticle: vi.fn(),
  updateAdminKnowledgeDocument: vi.fn(),
  uploadAdminKnowledgeDocuments: vi.fn()
}));

vi.mock("../lib/api", () => api);
vi.mock("../contexts/RoleContext", () => ({ useRole: () => ({ role: "admin" }) }));

const article = {
  body: "Use verified project details only.",
  category: "Support",
  id: 1,
  keywords: ["project"],
  status: "Published",
  summary: "Verified project guidance",
  title: "Project guidance",
  url: ""
};

const document = {
  body: "Internal guidance",
  category: "Knowledge",
  created_at: "2026-10-07T08:00:00Z",
  id: 2,
  source_name: "https://support.example.test/project",
  source_type: "url",
  status: "Published",
  summary: "Imported guidance",
  tags: ["support"],
  title: "Support page",
  updated_at: "2026-10-07T09:00:00Z"
};

function renderTeachAi() {
  return render(<MemoryRouter><AIAgentPage embedded /></MemoryRouter>);
}

describe("Phase 6B Teach AI, Articles, and Training Documents", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    api.getAdminArticles.mockResolvedValue({ articles: [article] });
    api.getAdminKnowledgeDocuments.mockResolvedValue({ documents: [document] });
    api.getSupportAssist.mockResolvedValue({
      answer: "Here is the verified guidance.",
      matched_chunks: [
        { chunk_id: 1, record_id: 1, record_kind: "knowledge", source_name: "Support page", title: "Imported guidance" },
        { project_name: "Returned project", record_kind: "company_api", title: "Project record" }
      ],
      source_label: "Workspace knowledge"
    });
    api.uploadAdminKnowledgeDocuments.mockResolvedValue({ documents: [document], files: [{ document_count: 1, file_name: "guide.txt" }] });
    api.deleteAdminKnowledgeDocuments.mockResolvedValue({ deleted_count: 1 });
    api.createAdminArticle.mockResolvedValue({ article });
    api.createAdminKnowledgeDocument.mockResolvedValue({ document });
    api.updateAdminArticle.mockResolvedValue({ article });
    api.updateAdminKnowledgeDocument.mockResolvedValue({ document });
  });

  it("renders only evidence fields returned by the current assist contract", async () => {
    renderTeachAi();
    await screen.findByText("https://example.test");
    fireEvent.change(screen.getByLabelText("Customer question"), { target: { value: "What guidance applies?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask AI now" }));

    expect(await screen.findByText("Imported guidance")).toBeInTheDocument();
    expect(screen.getByText("Project record")).toBeInTheDocument();
    expect(screen.getByText("Support page")).toBeInTheDocument();
    expect(screen.queryByText("No handoff needed.")).not.toBeInTheDocument();
  });

  it("keeps file upload and integrated-link deletion on their existing APIs", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderTeachAi();
    await screen.findByText("https://example.test");

    const file = new File(["guide"], "guide.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("Training files"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload and teach AI" }));
    await waitFor(() => expect(api.uploadAdminKnowledgeDocuments).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.deleteAdminKnowledgeDocuments).toHaveBeenCalledWith([2]));
  });

  it("keeps Articles and Training Documents as separately labelled libraries", async () => {
    render(<ArticlesPage embedded />);

    expect(await screen.findByRole("heading", { name: "Articles and training", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Article Library")).toBeInTheDocument();
    expect(screen.getByText("Training Documents")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Search articles" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Search training documents" })).toBeInTheDocument();
  });

  it("updates an article without routing it through the training-document API", async () => {
    render(<ArticlesPage embedded />);
    await screen.findByText("Project guidance");
    fireEvent.click(screen.getAllByRole("button", { name: "Manage" })[0]);
    fireEvent.change(screen.getByLabelText("Body"), { target: { value: "Updated verified guidance" } });
    fireEvent.click(screen.getByRole("button", { name: "Save article" }));

    await waitFor(() => expect(api.updateAdminArticle).toHaveBeenCalledWith(1, expect.objectContaining({ body: "Updated verified guidance" })));
    expect(api.updateAdminKnowledgeDocument).not.toHaveBeenCalled();
  });

  it("uploads training files as draft documents without changing article data", async () => {
    render(<ArticlesPage embedded />);
    await screen.findByText("Training Documents");
    const file = new File(["policy"], "policy.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("Upload files"), { target: { files: [file] } });

    await waitFor(() => expect(api.uploadAdminKnowledgeDocuments).toHaveBeenCalledWith(expect.objectContaining({ status: "Draft" })));
    expect(api.createAdminArticle).not.toHaveBeenCalled();
  });
});
