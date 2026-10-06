import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { GridViewIcon, ListViewIcon, SearchIcon } from "./chat/ChatIcons";

type BreadcrumbItem = {
  label: string;
  to?: string;
};

type HelpCenterBreadcrumbsProps = {
  items: BreadcrumbItem[];
};

type HelpCenterSearchProps = {
  compact?: boolean;
  label: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder: string;
  showClear?: boolean;
  value: string;
};

type HelpCenterViewToggleProps = {
  label: string;
  onChange: (view: "grid" | "list") => void;
  value: "grid" | "list";
};

export function HelpCenterBreadcrumbs({ items }: HelpCenterBreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb" className="help-center-breadcrumbs">
      <ol>
        {items.map((item, index) => {
          const isCurrent = index === items.length - 1;

          return (
            <li key={`${item.label}-${index}`}>
              {item.to && !isCurrent ? (
                <Link to={item.to}>{item.label}</Link>
              ) : (
                <span aria-current={isCurrent ? "page" : undefined}>{item.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function HelpCenterSearch({
  compact = false,
  label,
  onChange,
  onSubmit,
  placeholder,
  showClear = false,
  value
}: HelpCenterSearchProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form
      aria-label={label}
      className={compact ? "help-center-subpage-search" : "help-center-search-shell"}
      onSubmit={handleSubmit}
      role="search"
    >
      <label className={`help-center-searchbar${compact ? " compact" : ""}`}>
        <span className="help-center-visually-hidden">{label}</span>
        <SearchIcon />
        <input
          aria-label={label}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          type="search"
          value={value}
        />
        {showClear && value.trim() ? (
          <button
            aria-label="Clear search"
            className="help-center-search-clear"
            onClick={() => onChange("")}
            type="button"
          >
            <span aria-hidden="true">×</span>
          </button>
        ) : null}
      </label>
    </form>
  );
}

export function HelpCenterViewToggle({ label, onChange, value }: HelpCenterViewToggleProps) {
  return (
    <div aria-label={label} className="help-center-view-toggle" role="group">
      <button
        aria-label="Grid view"
        aria-pressed={value === "grid"}
        className={`help-center-view-button${value === "grid" ? " active" : ""}`}
        onClick={() => onChange("grid")}
        type="button"
      >
        <GridViewIcon />
      </button>
      <button
        aria-label="List view"
        aria-pressed={value === "list"}
        className={`help-center-view-button${value === "list" ? " active" : ""}`}
        onClick={() => onChange("list")}
        type="button"
      >
        <ListViewIcon />
      </button>
    </div>
  );
}
