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
      quickReplies: [{ label: "Acro Iris", value: "Acro Iris" }, { label: "Acro Tulip", value: "Acro Tulip" }]
    })).toBe("Choose a project:");

    expect(visibleMessageText({
      ...fallbackList,
      quickReplies: [{ action: "browse_projects", label: "Browse", value: "Show me all projects" }]
    })).toBe(fallbackList.text);
  });

  it("keeps bullet content that is not purely a restated quick-reply label", () => {
    // A bulleted line with its own content (price, disclaimer, closing prompt)
    // must survive even though the same project names are offered as buttons.
    const shortlist = {
      ...projectChoices,
      text: [
        "2BHK projects (estimated base amount):",
        "- Acro Iris: estimated base amount from INR 50.00 lakh",
        "- Acro Tulip: estimated base amount from INR 60.00 lakh",
        "",
        "Estimated base amount excludes taxes, registration, floor rise and parking.",
        "",
        "Select a project and I'll check its current details and availability.",
      ].join("\n"),
      quickReplies: [{ label: "Acro Iris", value: "Acro Iris" }, { label: "Acro Tulip", value: "Acro Tulip" }]
    };
    expect(visibleMessageText(shortlist)).toBe(shortlist.text);
  });

  it("keeps a fallback list unabridged when a quick reply only partially covers the bullets", () => {
    const partiallyCovered = {
      ...projectChoices,
      text: "Choose a project:\n- Acro Iris\n- Acro Tulip",
      quickReplies: [{ label: "Acro Iris", value: "Acro Iris" }]
    };
    expect(visibleMessageText(partiallyCovered)).toBe(partiallyCovered.text);
  });

  it("shows the discovery question and qualifier with live area buttons plus Any area", () => {
    const localityTurn: ChatContractMessage = {
      isComplete: true,
      sender: "bot",
      text: [
        "We have two projects listing 3BHK homes in Pune and Thane.",
        "These are catalogue listings; I haven't checked current unit availability yet.",
        'Which location would you like to explore? You can also say "any area".',
        "- Pune",
        "- Thane"
      ].join("\n"),
      quickReplies: [
        { label: "Pune", value: "Pune" },
        { label: "Thane", value: "Thane" },
        { label: "Any area", value: "Any area" }
      ]
    };
    expect(visibleMessageText(localityTurn)).toContain("Which location would you like to explore?");
    expect(visibleMessageText(localityTurn)).toContain("I haven't checked current unit availability yet.");
    expect(visibleMessageText(localityTurn)).not.toContain("- Pune");
    expect(getQuickReplyDispatch(localityTurn.quickReplies![2], localityTurn)).toEqual({
      customerMessageText: "Any area", issue: "Any area", kind: "assist", resetConversation: false
    });
  });

  it("shows the full budget prompt and dispatches its wildcard as free text", () => {
    const budgetTurn: ChatContractMessage = {
      isComplete: true,
      sender: "bot",
      text: "We have one project listed with 3BHK configurations in Pune.\nDo you have a budget limit, or should I include all prices?\nFeel free to type your budget in the chat.",
      quickReplies: [{ label: "Any budget", value: "any budget" }]
    };
    expect(visibleMessageText(budgetTurn)).toBe(budgetTurn.text);
    expect(getQuickReplyDispatch(budgetTurn.quickReplies![0], budgetTurn)).toEqual({
      customerMessageText: "any budget", issue: "any budget", kind: "assist", resetConversation: false
    });
    expect(resolveProjectSelection([budgetTurn], "1")).toBe("");
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
