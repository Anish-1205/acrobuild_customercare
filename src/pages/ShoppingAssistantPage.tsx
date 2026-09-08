import { useNavigate } from "react-router-dom";
import {
  TrainActionGrid,
  TrainChoiceGrid,
  TrainHero,
  TrainPanel,
  TrainSplitCallout
} from "../components/TrainUi";
import { useRole } from "../contexts/RoleContext";
import {
  getRolePanelPath,
  type WorkspacePanelId
} from "../lib/roleNavigation";

type ShoppingAssistantPageProps = {
  embedded?: boolean;
};

type AssistantCard = {
  button_label: string;
  copy: string;
  label: string;
  panel?: WorkspacePanelId;
  target?: "test";
};

const assistantCards: AssistantCard[] = [
  {
    label: "Knowledge",
    copy: "Check if the AI already knows the product and support answers.",
    button_label: "Open knowledge",
    panel: "knowledge-base"
  },
  {
    label: "Support Actions",
    copy: "Set the safety rules before the AI talks to customers.",
    button_label: "Open support actions",
    panel: "support-actions"
  },
  {
    label: "Test AI",
    copy: "Ask one customer question before turning on live chat.",
    button_label: "Open test AI",
    target: "test"
  },
  {
    label: "Chat setup",
    copy: "Set chat width, appearance, and turn on the customer chat experience.",
    button_label: "Open chat setup",
    panel: "chat-widget"
  }
];

export function ShoppingAssistantPage({ embedded = false }: ShoppingAssistantPageProps) {
  const navigate = useNavigate();
  const { role } = useRole();

  function buildPanelPathWithParams(
    panel: WorkspacePanelId,
    params: Record<string, string>
  ) {
    const basePath = getRolePanelPath(role, panel);
    const [pathname, rawSearch = ""] = basePath.split("?");
    const nextSearchParams = new URLSearchParams(rawSearch);

    Object.entries(params).forEach(([key, value]) => {
      if (value.trim()) {
        nextSearchParams.set(key, value);
        return;
      }

      nextSearchParams.delete(key);
    });

    const nextQuery = nextSearchParams.toString();
    return nextQuery ? `${pathname}?${nextQuery}` : pathname;
  }

  function openPanel(panel: WorkspacePanelId) {
    if (panel === "knowledge-base") {
      navigate(buildPanelPathWithParams(panel, { trainView: "knowledge" }));
      return;
    }

    if (panel === "chat-widget") {
      navigate(buildPanelPathWithParams(panel, { trainView: "shopping-assistant" }));
      return;
    }

    navigate(getRolePanelPath(role, panel));
  }

  function openTest() {
    navigate(
      buildPanelPathWithParams("knowledge-base", {
        train: "test",
        trainView: "shopping-assistant"
      })
    );
  }

  return (
    <div className="stack-page ai-agent-page train-ui-page">
      <TrainHero
        actionLabel="Go to test AI"
        description="This page is for live customer chat. Turn it on only after testing."
        eyebrow={embedded ? "Shopping assistant workspace" : "Train"}
        onAction={openTest}
        stats={[
          {
            label: "Steps",
            note: "Do these before live chat",
            value: 4
          },
          {
            label: "Important",
            note: "Never skip this",
            value: "Test"
          },
          {
            label: "Goal",
            note: "Safe live customer chat",
            value: "Live"
          }
        ]}
        tip="Test the AI before you turn on chat setup."
        title="Turn on customer chat"
      />

      <TrainPanel
        description="Follow the order below if you want to launch the customer chat safely."
        eyebrow="Step by step"
        title="Open these pages in order"
      >
        <TrainActionGrid
          items={assistantCards.map((card, index) => ({
            badge: `Step ${index + 1}`,
            buttonLabel: card.button_label,
            description: card.copy,
            onClick: () => {
              if (card.target === "test") {
                openTest();
                return;
              }

              if (card.panel) {
                openPanel(card.panel);
              }
            },
            title: card.label
          }))}
        />
      </TrainPanel>

      <TrainPanel
        description="Think of these pages like a small launch checklist."
        eyebrow="Launch checklist"
        title="What each page helps you do"
      >
        <TrainChoiceGrid
          items={[
            {
              badge: "Learn",
              description: "Check whether the AI already knows product and support answers.",
              onClick: () => openPanel("knowledge-base"),
              title: "Knowledge"
            },
            {
              badge: "Safe",
              description: "Set the safety rules before the AI talks to customers.",
              onClick: () => openPanel("support-actions"),
              title: "Support Actions"
            },
            {
              badge: "Live",
              description: "Set chat size, look, and turn on the customer chat experience.",
              onClick: () => openPanel("chat-widget"),
              title: "Chat setup"
            }
          ]}
        />
      </TrainPanel>

      <TrainSplitCallout
        actionLabel="Open chat setup"
        description="For most teams: Knowledge, then Support Actions, then Test AI, then Chat setup."
        eyebrow="Quick start"
        onAction={() => openPanel("chat-widget")}
        title="Best order for most teams"
      />
    </div>
  );
}
