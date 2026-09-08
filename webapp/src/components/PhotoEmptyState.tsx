type PhotoEmptyStateProps = {
  className?: string;
  description: string;
  highlights?: string[];
  eyebrow?: string;
  imageAlt?: string;
  imageSrc?: string;
  title: string;
  variant?: "compact" | "media";
};

export function PhotoEmptyState({
  className = "",
  description,
  highlights = [],
  eyebrow = "Workspace view",
  imageAlt,
  imageSrc,
  title,
  variant = "compact"
}: PhotoEmptyStateProps) {
  return (
    <div className={`photo-empty-state ${variant}${className ? ` ${className}` : ""}`}>
      <div className="photo-empty-state-copy">
        <div className="photo-empty-state-badge" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div className="photo-empty-state-eyebrow">{eyebrow}</div>
        <strong>{title}</strong>
        <p>{description}</p>

        {highlights.length ? (
          <div className="photo-empty-state-highlights">
            {highlights.map((item) => (
              <span className="photo-empty-state-chip" key={item}>
                {item}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {variant === "media" && imageSrc ? (
        <div className="photo-empty-state-media">
          <img alt={imageAlt || ""} src={imageSrc} />
        </div>
      ) : null}
    </div>
  );
}
