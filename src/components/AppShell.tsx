import {
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent
} from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { useRole } from "../contexts/RoleContext";
import { useSearch } from "../contexts/SearchContext";
import { getRoleHomePath, roleExperienceMap } from "../lib/roleNavigation";

export function AppShell() {
  const navigate = useNavigate();
  const { currentUser, logout, role } = useRole();
  const {
    searchSuggestions,
    ticketSearchQuery,
    setTicketSearchQuery,
    visibleTicketCount
  } = useSearch();
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [highlightedSuggestionId, setHighlightedSuggestionId] = useState("");
  const [floatingSuggestionStyle, setFloatingSuggestionStyle] = useState<CSSProperties>({});
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const roleExperience = roleExperienceMap[role];
  const searchPlaceholder =
    role === "agent"
      ? "Search tickets by ticket ID"
      : "Search tickets by ticket ID, customer, or email";
  const normalizedQuery = ticketSearchQuery.trim().toLowerCase();
  const filteredSuggestions = useMemo(() => {
    if (!normalizedQuery) {
      return [];
    }

    return searchSuggestions
      .filter((suggestion) => suggestion.searchText.includes(normalizedQuery))
      .sort((left, right) => {
        const leftPrimary = left.primary.toLowerCase();
        const rightPrimary = right.primary.toLowerCase();
        const leftRank = leftPrimary.startsWith(normalizedQuery) ? 0 : leftPrimary.includes(normalizedQuery) ? 1 : 2;
        const rightRank = rightPrimary.startsWith(normalizedQuery) ? 0 : rightPrimary.includes(normalizedQuery) ? 1 : 2;

        return leftRank - rightRank || leftPrimary.localeCompare(rightPrimary);
      })
      .slice(0, 7);
  }, [normalizedQuery, searchSuggestions]);
  const shouldShowSuggestions = isSearchFocused && filteredSuggestions.length > 0;

  useEffect(() => {
    if (!shouldShowSuggestions) {
      setHighlightedSuggestionId("");
      return;
    }

    setHighlightedSuggestionId((current) => {
      if (current && filteredSuggestions.some((suggestion) => suggestion.id === current)) {
        return current;
      }

      return filteredSuggestions[0]?.id ?? "";
    });
  }, [filteredSuggestions, shouldShowSuggestions]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!searchContainerRef.current?.contains(event.target as Node)) {
        setIsSearchFocused(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  useEffect(() => {
    if (!shouldShowSuggestions) {
      return;
    }

    function updateSuggestionPosition() {
      const container = searchContainerRef.current;

      if (!container) {
        return;
      }

      const bounds = container.getBoundingClientRect();
      const sidebar = document.querySelector(".support-console-sidebar");
      const sidebarBounds = sidebar instanceof HTMLElement ? sidebar.getBoundingClientRect() : null;
      const minLeft = sidebarBounds ? sidebarBounds.right + 12 : bounds.left;
      const nextLeft = Math.max(bounds.left, minLeft);
      const nextWidth = Math.max(260, bounds.right - nextLeft);

      setFloatingSuggestionStyle({
        left: nextLeft,
        top: bounds.bottom + 8,
        width: nextWidth
      });
    }

    updateSuggestionPosition();

    window.addEventListener("resize", updateSuggestionPosition);
    window.addEventListener("scroll", updateSuggestionPosition, true);

    return () => {
      window.removeEventListener("resize", updateSuggestionPosition);
      window.removeEventListener("scroll", updateSuggestionPosition, true);
    };
  }, [shouldShowSuggestions]);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  function handleSuggestionSelect(value: string) {
    setTicketSearchQuery(value);
    setIsSearchFocused(false);
  }

  function handleSearchKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (!shouldShowSuggestions) {
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();

      const currentIndex = filteredSuggestions.findIndex((suggestion) => suggestion.id === highlightedSuggestionId);
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex =
        currentIndex === -1
          ? 0
          : (currentIndex + direction + filteredSuggestions.length) % filteredSuggestions.length;

      setHighlightedSuggestionId(filteredSuggestions[nextIndex]?.id ?? "");
      return;
    }

    if (event.key === "Enter") {
      const highlightedSuggestion = filteredSuggestions.find(
        (suggestion) => suggestion.id === highlightedSuggestionId
      );

      if (highlightedSuggestion) {
        event.preventDefault();
        handleSuggestionSelect(highlightedSuggestion.value);
      }

      return;
    }

    if (event.key === "Escape") {
      setIsSearchFocused(false);
    }
  }

  return (
    <div className={`support-console-shell support-console-shell-${role}`}>
      <header className="support-shell-bar">
        <Link aria-label={`${roleExperience.shortLabel} home`} className="support-shell-brand" to={getRoleHomePath(role)}>
          <div className="support-shell-brand-mark">{roleExperience.shortLabel.slice(0, 2).toUpperCase()}</div>
          <div>
            <div className="support-shell-kicker">{roleExperience.shortLabel} Experience</div>
            <div className="support-shell-title">{roleExperience.shortLabel}</div>
          </div>
        </Link>

        <div className="support-shell-search-container">
          <div className="support-shell-searchbox" ref={searchContainerRef}>
            <label className="support-shell-searchbar">
              <span className="support-shell-search-icon" aria-hidden="true">
                &#9906;
              </span>
              <input
                aria-expanded={shouldShowSuggestions}
                aria-haspopup="listbox"
                className="support-shell-search-input"
                onChange={(event) => setTicketSearchQuery(event.target.value)}
                onFocus={() => setIsSearchFocused(true)}
                onKeyDown={handleSearchKeyDown}
                placeholder={searchPlaceholder}
                type="search"
                value={ticketSearchQuery}
              />
            </label>

            {shouldShowSuggestions ? (
              <div className="support-shell-suggestions" role="listbox" style={floatingSuggestionStyle}>
                {filteredSuggestions.map((suggestion) => (
                  <button
                    className={`support-shell-suggestion${suggestion.id === highlightedSuggestionId ? " active" : ""}`}
                    key={suggestion.id}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      handleSuggestionSelect(suggestion.value);
                    }}
                    type="button"
                  >
                    <span className={`support-shell-suggestion-kind ${suggestion.kind}`}>
                      {suggestion.kind}
                    </span>
                    <span className="support-shell-suggestion-copy">
                      <strong>{suggestion.primary}</strong>
                      <small>{suggestion.secondary}</small>
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          {visibleTicketCount > 0 ? (
            <div className="support-shell-search-meta">
              {visibleTicketCount} ticket{visibleTicketCount === 1 ? "" : "s"}
            </div>
          ) : null}
        </div>

        <div className="support-shell-toolbar">
          {role !== "agent" && <Link className="support-shell-link" to={`/${role}/automation`}>Automations</Link>}
          {role === "admin" ? (
            <a
              className="support-shell-link support-shell-test-home"
              href="/home"
              rel="noreferrer"
              target="_blank"
            >
              Test Home
            </a>
          ) : null}
          <div className="support-shell-session">
            <div className="support-shell-session-copy">
              <strong>{currentUser?.name ?? roleExperience.label}</strong>
              <span>{currentUser?.email ?? roleExperience.shortLabel}</span>
            </div>
            <span className="support-shell-session-role">{roleExperience.shortLabel}</span>
            <button className="support-shell-link support-shell-link-secondary" onClick={handleLogout} type="button">
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="page-shell support-console-page-shell">
        <Outlet />
      </main>
    </div>
  );
}


