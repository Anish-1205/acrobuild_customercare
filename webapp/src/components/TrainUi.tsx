import type { ReactNode } from "react";

type TrainStat = {
  label: string;
  note?: string;
  value: number | string;
};

type TrainHeroProps = {
  actionLabel?: string;
  description: string;
  eyebrow: string;
  onAction?: () => void;
  stats?: TrainStat[];
  tip?: string;
  title: string;
};

type TrainPanelProps = {
  children: ReactNode;
  className?: string;
  description?: string;
  eyebrow: string;
  title: string;
};

type TrainActionItem = {
  badge: string;
  buttonLabel: string;
  description: string;
  helper?: string;
  onClick: () => void;
  title: string;
};

type TrainActionGridProps = {
  items: TrainActionItem[];
};

type TrainChoiceItem = {
  badge?: string;
  buttonLabel?: string;
  description: string;
  onClick?: () => void;
  title: string;
};

type TrainChoiceGridProps = {
  items: TrainChoiceItem[];
};

type TrainSplitCalloutProps = {
  actionLabel: string;
  description: string;
  eyebrow: string;
  onAction: () => void;
  title: string;
};

export function TrainHero({
  actionLabel,
  description,
  eyebrow,
  onAction,
  stats = [],
  tip,
  title
}: TrainHeroProps) {
  return (
    <section className="train-ui-hero">
      <div className="train-ui-hero-copy">
        <div className="train-ui-eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
        <p>{description}</p>

        {tip ? <div className="train-ui-tip">{tip}</div> : null}

        {actionLabel && onAction ? (
          <div className="train-ui-hero-actions">
            <button className="primary-button train-ui-primary-action" onClick={onAction} type="button">
              {actionLabel}
            </button>
          </div>
        ) : null}
      </div>

      <div className="train-ui-hero-side">
        <div className="train-ui-hero-photo-card">
          <img
            alt="Support lead reviewing knowledge and workflow notes with a teammate"
            className="train-ui-hero-photo"
            src="/images/real-world/ai-training.png"
          />
          <div className="train-ui-hero-photo-note">
            <strong>Ground the AI in real support work</strong>
            <span>Policies, answers, files, and workflows your team already trusts.</span>
          </div>
        </div>

        {stats.length ? (
          <div className="train-ui-stat-grid">
            {stats.map((stat) => (
              <div className="train-ui-stat-card" key={stat.label}>
                <span>{stat.label}</span>
                <strong>{stat.value}</strong>
                {stat.note ? <small>{stat.note}</small> : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function TrainPanel({
  children,
  className = "",
  description,
  eyebrow,
  title
}: TrainPanelProps) {
  return (
    <section className={`train-ui-panel${className ? ` ${className}` : ""}`}>
      <div className="train-ui-panel-head">
        <div className="train-ui-eyebrow">{eyebrow}</div>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>

      {children}
    </section>
  );
}

export function TrainActionGrid({ items }: TrainActionGridProps) {
  return (
    <div className="train-ui-action-grid">
      {items.map((item) => (
        <article className="train-ui-action-card" key={`${item.badge}-${item.title}`}>
          <div className="train-ui-card-badge">{item.badge}</div>
          <strong>{item.title}</strong>
          <p>{item.description}</p>
          <button className="primary-button train-ui-card-button" onClick={item.onClick} type="button">
            {item.buttonLabel}
          </button>
          {item.helper ? <div className="train-ui-card-helper">{item.helper}</div> : null}
        </article>
      ))}
    </div>
  );
}

export function TrainChoiceGrid({ items }: TrainChoiceGridProps) {
  return (
    <div className="train-ui-choice-grid">
      {items.map((item) => {
        const content = (
          <>
            {item.badge ? <div className="train-ui-choice-badge">{item.badge}</div> : null}
            <strong>{item.title}</strong>
            <span>{item.description}</span>
            {item.buttonLabel ? <small>{item.buttonLabel}</small> : null}
          </>
        );

        if (item.onClick) {
          return (
            <button className="train-ui-choice-card" key={`${item.badge || "choice"}-${item.title}`} onClick={item.onClick} type="button">
              {content}
            </button>
          );
        }

        return (
          <article className="train-ui-choice-card static" key={`${item.badge || "choice"}-${item.title}`}>
            {content}
          </article>
        );
      })}
    </div>
  );
}

export function TrainSplitCallout({
  actionLabel,
  description,
  eyebrow,
  onAction,
  title
}: TrainSplitCalloutProps) {
  return (
    <section className="train-ui-callout">
      <div>
        <div className="train-ui-eyebrow">{eyebrow}</div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>

      <div className="train-ui-callout-action">
        <button className="primary-button train-ui-primary-action" onClick={onAction} type="button">
          {actionLabel}
        </button>
      </div>
    </section>
  );
}
