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

type SupportActionsPageProps = {
  embedded?: boolean;
};

type ActionCard = {
  button_label: string;
  copy: string;
  label: string;
  panel: WorkspacePanelId;
  step: string;
};

const actionCards: ActionCard[] = [
  {
    step: "Step 1",
    label: "Rules",
    copy: "Choose when the AI can answer and when a person must help.",
    button_label: "Open rules",
    panel: "rules"
  },
  {
    step: "Step 2",
    label: "Business Hours",
    copy: "Choose what happens during business hours and after hours.",
    button_label: "Open business hours",
    panel: "business-hours"
  },
  {
    step: "Step 3",
    label: "Macros",
    copy: "Save ready-made replies and support steps for your team.",
    button_label: "Open macros",
    panel: "macros"
  }
];

export function SupportActionsPage({ embedded = false }: SupportActionsPageProps) {
  const navigate = useNavigate();
  const { role } = useRole();

  function openPanel(panel: WorkspacePanelId) {
    navigate(getRolePanelPath(role, panel));
  }

  return (
    <div className="stack-page ai-agent-page train-ui-page">
      <TrainHero
        actionLabel="Start with rules"
        description="Use this page to tell the AI when it can answer and when a person must help."
        eyebrow={embedded ? "Support actions workspace" : "Train"}
        onAction={() => openPanel("rules")}
        stats={[
          {
            label: "Pages",
            note: "Three small setup pages",
            value: 3
          },
          {
            label: "Start here",
            note: "Most important first click",
            value: "Rules"
          },
          {
            label: "Goal",
            note: "Make AI safe before live chat",
            value: "Safe"
          }
        ]}
        tip="Do not teach answers here. This page is only for safety."
        title="Make AI safe"
      />

      <TrainPanel
        description="Each page below has one job. Open the first one first."
        eyebrow="Step by step"
        title="Open these 3 pages"
      >
        <TrainActionGrid
          items={actionCards.map((card) => ({
            badge: card.step,
            buttonLabel: card.button_label,
            description: card.copy,
            onClick: () => openPanel(card.panel),
            title: card.label
          }))}
        />
      </TrainPanel>

      <TrainPanel
        description="These words are easier if you think of them like this."
        eyebrow="Simple meaning"
        title="What each page really does"
      >
        <TrainChoiceGrid
          items={[
            {
              badge: "1",
              description: "Choose when the AI may answer and when it must stop for a person.",
              onClick: () => openPanel("rules"),
              title: "Rules"
            },
            {
              badge: "2",
              description: "Decide what happens during open hours and after hours.",
              onClick: () => openPanel("business-hours"),
              title: "Business Hours"
            },
            {
              badge: "3",
              description: "Save team replies and support steps people can reuse fast.",
              onClick: () => openPanel("macros"),
              title: "Macros"
            }
          ]}
        />
      </TrainPanel>

      <TrainSplitCallout
        actionLabel="Open rules"
        description="For most teams: Rules first, then Business Hours, then Macros."
        eyebrow="Quick start"
        onAction={() => openPanel("rules")}
        title="Best order for most teams"
      />
    </div>
  );
}
