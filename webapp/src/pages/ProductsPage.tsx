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

type ProductsPageProps = {
  embedded?: boolean;
};

type ProductCard = {
  button_label: string;
  copy: string;
  label: string;
  target: "file" | "test" | "url" | "website";
};

const productCards: ProductCard[] = [
  {
    label: "Website pages",
    copy: "Use this when your products are already on your website.",
    button_label: "Open website pages",
    target: "website"
  },
  {
    label: "One link",
    copy: "Use this when you only have one product page or one policy page.",
    button_label: "Open one link",
    target: "url"
  },
  {
    label: "Upload file",
    copy: "Use this for product PDF, menu, catalog, or any document file.",
    button_label: "Open upload file",
    target: "file"
  },
  {
    label: "Test product answer",
    copy: "Ask one sample product question and see what the AI says.",
    button_label: "Open product test",
    target: "test"
  }
];

export function ProductsPage({ embedded = false }: ProductsPageProps) {
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

  function openKnowledgeTarget(target: ProductCard["target"]) {
    navigate(
      buildPanelPathWithParams("knowledge-base", {
        train: target,
        trainView: "products"
      })
    );
  }

  return (
    <div className="stack-page ai-agent-page train-ui-page">
      <TrainHero
        actionLabel="Start with website pages"
        description="Use the place where your product details already live."
        eyebrow={embedded ? "Products workspace" : "Train"}
        onAction={() => openKnowledgeTarget("website")}
        stats={[
          {
            label: "Ways to add",
            note: "Website, one link, file, or test",
            value: 4
          },
          {
            label: "Best first step",
            note: "Easiest for most shops",
            value: "Website"
          },
          {
            label: "Goal",
            note: "Answer product questions better",
            value: "Info"
          }
        ]}
        tip="If your products are already on your website, start with Website pages first."
        title="Add product info"
      />

      <TrainPanel
        description="Pick only one option below based on where your product information lives."
        eyebrow="Step by step"
        title="Choose one product source"
      >
        <TrainActionGrid
          items={productCards.map((card, index) => ({
            badge: `Step ${index + 1}`,
            buttonLabel: card.button_label,
            description: card.copy,
            onClick: () => openKnowledgeTarget(card.target),
            title: card.label
          }))}
        />
      </TrainPanel>

      <TrainPanel
        description="Use the card that matches where your real product details already exist."
        eyebrow="Pick the right source"
        title="What each option means"
      >
        <TrainChoiceGrid
          items={[
            {
              badge: "Best",
              description: "Use this when most product details are already on your website.",
              onClick: () => openKnowledgeTarget("website"),
              title: "Website pages"
            },
            {
              badge: "One page",
              description: "Use this when you only have one product page or one policy page.",
              onClick: () => openKnowledgeTarget("url"),
              title: "One link"
            },
            {
              badge: "Document",
              description: "Use this for PDF, menu, price list, or product document.",
              onClick: () => openKnowledgeTarget("file"),
              title: "Upload file"
            }
          ]}
        />
      </TrainPanel>

      <TrainSplitCallout
        actionLabel="Go to product test"
        description="For most shops: Website pages first, One link if needed, then Test product answer."
        eyebrow="Quick start"
        onAction={() => openKnowledgeTarget("test")}
        title="Best order for most shops"
      />
    </div>
  );
}
