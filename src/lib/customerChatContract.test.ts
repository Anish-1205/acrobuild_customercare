import { describe, expect, it } from "vitest";
import {
  getNamedProjectSelection,
  getNumberedProjectSelection,
  getQuickReplyDispatch,
  resolveProjectSelection,
  visibleMessageText,
  type ChatContractMessage
} from "./customerChatContract";

const projectChoices: ChatContractMessage = {
  isComplete: true,
  sender: "bot",
  text: "Choose a project:\n1. Acro Iris\n2) Acro Tulip"
};

describe("customer chat contract helpers", () => {
  it("shows only the prompt when passive quick replies duplicate a fallback list", () => {
    const fallbackList = { ...projectChoices, text: "Choose a project:\n- Acro Iris\n- Acro Tulip" };
    expect(visibleMessageText({
      ...fallbackList,
      quickReplies: [{ label: "Acro Iris", value: "Acro Iris" }]
    })).toBe("Choose a project:");

    expect(visibleMessageText({
      ...fallbackList,
      quickReplies: [{ action: "browse_projects", label: "Browse", value: "Show me all projects" }]
    })).toBe(fallbackList.text);
  });

  it("resolves exact named and numbered project selections from completed bot choices", () => {
    expect(getNamedProjectSelection([projectChoices], "acro tulip")).toBe("Acro Tulip");
    expect(getNumberedProjectSelection([projectChoices], "project number 1")).toBe("Acro Iris");
    expect(resolveProjectSelection([projectChoices], "2")).toBe("Acro Tulip");
  });

  it("gives server quick replies precedence over legacy text-list selection parsing", () => {
    const withServerChoices = {
      ...projectChoices,
      quickReplies: [{ label: "Acro Iris", value: "Acro Iris" }]
    };
    expect(resolveProjectSelection([withServerChoices], "1")).toBe("");
    expect(resolveProjectSelection([withServerChoices], "Acro Iris")).toBe("");
  });

  it("dispatches action replies without changing their intended targets", () => {
    expect(getQuickReplyDispatch(
      { action: "ticket", label: "Raise a ticket", value: "Raise a support ticket" },
      { contextIssue: "Original issue", text: "Bot answer" }
    )).toEqual({ kind: "ticket", issue: "Original issue" });
    expect(getQuickReplyDispatch(
      { action: "site_visit", label: "Book", project_name: "Acro Iris", value: "Book a site visit" },
      { text: "Bot answer" }
    )).toEqual({ kind: "site_visit", projectName: "Acro Iris" });
  });

  it("resets only catalogue browsing and submits ordinary reply values exactly", () => {
    expect(getQuickReplyDispatch(
      { action: "browse_projects", label: "Browse all projects", value: "Show me all projects" },
      { text: "Bot answer" }
    )).toEqual({
      customerMessageText: "Browse all projects",
      issue: "Show me all projects",
      kind: "assist",
      resetConversation: true
    });
    expect(getQuickReplyDispatch(
      { label: "Any budget", value: "any budget" },
      { text: "Bot answer" }
    )).toEqual({
      customerMessageText: "any budget",
      issue: "any budget",
      kind: "assist",
      resetConversation: false
    });
  });
});
