import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AcrobuildLogo } from "./AcrobuildLogo";
import { useRole } from "../contexts/RoleContext";
import { useSearch } from "../contexts/SearchContext";
import {
  getRoleHomePath,
  getRolePanelPath,
  getStaffNavigationItems,
  getWorkspacePanelFromLocation,
  roleExperienceMap
} from "../lib/roleNavigation";

const navigationSectionLabels = {
  workspace: "Workspace",
  manage: "Manage",
  system: "System"
} as const;

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser, logout, role } = useRole();
  const {
    searchSuggestions,
    ticketSearchQuery,
    setTicketSearchQuery,
    visibleTicketCount
  } = useSearch();
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [highlightedSuggestionId, setHighlightedSuggestionId] = useState("");
  const [isNavigationCollapsed, setIsNavigationCollapsed] = useState(false);
  const [isMobileNavigationOpen, setIsMobileNavigationOpen] = useState(false);
  const [isCompactViewport, setIsCompactViewport] = useState(false);
  const navigationRef = useRef<HTMLElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const roleExperience = roleExperienceMap[role];
  const navigationItems = getStaffNavigationItems(role);
  const activePanel = getWorkspacePanelFromLocation(location.pathname, location.search);
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
    setIsMobileNavigationOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }

    const compactViewport = window.matchMedia("(max-width: 820px)");
    const updateViewportMode = () => setIsCompactViewport(compactViewport.matches);

    updateViewportMode();
    compactViewport.addEventListener("change", updateViewportMode);

    return () => compactViewport.removeEventListener("change", updateViewportMode);
  }, []);

  useEffect(() => {
    if (navigationRef.current) {
      navigationRef.current.inert = isCompactViewport && !isMobileNavigationOpen;
    }

    if (!isCompactViewport || !isMobileNavigationOpen) {
      return;
    }

    navigationRef.current?.querySelector<HTMLElement>("a[href]")?.focus();

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsMobileNavigationOpen(false);
        menuButtonRef.current?.focus();
      }
    }

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isCompactViewport, isMobileNavigationOpen]);

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
    <div className={`support-console-shell support-console-shell-${role}${isNavigationCollapsed ? " staff-navigation-collapsed" : ""}${isMobileNavigationOpen ? " staff-navigation-open" : ""}`}>
      <a className="staff-shell-skip-link" href="#staff-main-content">Skip to workspace</a>

      <aside
        aria-hidden={isCompactViewport && !isMobileNavigationOpen ? true : undefined}
        className="staff-shell-navigation"
        id="staff-navigation"
        ref={navigationRef}
      >
        <Link aria-label={`${roleExperience.shortLabel} home`} className="staff-shell-logo" to={getRoleHomePath(role)}>
          <AcrobuildLogo subtitle={`${roleExperience.shortLabel} workspace`} />
        </Link>

        <nav aria-label="Staff navigation" className="staff-shell-nav">
          {(["workspace", "manage", "system"] as const).map((section) => {
            const sectionItems = navigationItems.filter((item) => item.section === section);

            if (!sectionItems.length) {
              return null;
            }

            return (
              <div className="staff-shell-nav-section" key={section}>
                <div className="staff-shell-nav-label">{navigationSectionLabels[section]}</div>
                {sectionItems.map((item) => {
                  const isActive = activePanel ? item.activePanels.includes(activePanel) : false;

                  return (
                    <Link
                      aria-current={isActive ? "page" : undefined}
                      className={`staff-shell-nav-item${isActive ? " active" : ""}`}
                      key={item.panel}
                      title={isNavigationCollapsed ? item.label : undefined}
                      to={getRolePanelPath(role, item.panel)}
                    >
                      <span aria-hidden="true" className="staff-shell-nav-icon">{item.shortLabel}</span>
                      <span className="staff-shell-nav-copy">{item.label}</span>
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <button
          aria-label={isNavigationCollapsed ? "Expand navigation" : "Collapse navigation"}
          className="staff-shell-collapse"
          onClick={() => setIsNavigationCollapsed((current) => !current)}
          type="button"
        >
          <span aria-hidden="true">{isNavigationCollapsed ? ">" : "<"}</span>
          <span className="staff-shell-nav-copy">Collapse</span>
        </button>
      </aside>

      <button
        aria-label="Close navigation"
        className="staff-shell-scrim"
        onClick={() => {
          setIsMobileNavigationOpen(false);
          menuButtonRef.current?.focus();
        }}
        type="button"
      />

      <div className="staff-shell-workspace">
        <header className="support-shell-bar">
          <button
            aria-controls="staff-navigation"
            aria-expanded={isMobileNavigationOpen}
            aria-label="Open navigation"
            className="staff-shell-menu-button"
            onClick={() => setIsMobileNavigationOpen(true)}
            ref={menuButtonRef}
            type="button"
          >
            <span aria-hidden="true">&#9776;</span>
          </button>

          <div className="support-shell-search-container">
            <div className="support-shell-searchbox" ref={searchContainerRef}>
              <label className="support-shell-searchbar">
                <span className="support-shell-search-icon" aria-hidden="true">&#9906;</span>
                <input
                  aria-activedescendant={shouldShowSuggestions ? `staff-search-option-${highlightedSuggestionId}` : undefined}
                  aria-controls="staff-search-suggestions"
                  aria-expanded={shouldShowSuggestions}
                  aria-haspopup="listbox"
                  aria-label="Search tickets"
                  className="support-shell-search-input"
                  onChange={(event) => setTicketSearchQuery(event.target.value)}
                  onFocus={() => setIsSearchFocused(true)}
                  onKeyDown={handleSearchKeyDown}
                  placeholder={searchPlaceholder}
                  role="combobox"
                  type="search"
                  value={ticketSearchQuery}
                />
              </label>

              {shouldShowSuggestions ? (
                <div className="support-shell-suggestions" id="staff-search-suggestions" role="listbox">
                  {filteredSuggestions.map((suggestion) => (
                    <button
                      aria-selected={suggestion.id === highlightedSuggestionId}
                      className={`support-shell-suggestion${suggestion.id === highlightedSuggestionId ? " active" : ""}`}
                      id={`staff-search-option-${suggestion.id}`}
                      key={suggestion.id}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        handleSuggestionSelect(suggestion.value);
                      }}
                      role="option"
                      type="button"
                    >
                      <span className={`support-shell-suggestion-kind ${suggestion.kind}`}>{suggestion.kind}</span>
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
              <div className="support-shell-search-meta">{visibleTicketCount} ticket{visibleTicketCount === 1 ? "" : "s"}</div>
            ) : null}
          </div>

          <div className="support-shell-toolbar">
            {role === "admin" ? <a className="support-shell-link support-shell-test-home" href="/home" rel="noreferrer" target="_blank">Test Home</a> : null}
            <div className="support-shell-session">
              <div className="support-shell-session-copy">
                <strong>{currentUser?.name ?? roleExperience.label}</strong>
                <span>{currentUser?.email ?? roleExperience.shortLabel}</span>
              </div>
              <span className="support-shell-session-role">{roleExperience.shortLabel}</span>
              <button className="support-shell-link support-shell-link-secondary" onClick={handleLogout} type="button">Log out</button>
            </div>
          </div>
        </header>

        <main className="page-shell support-console-page-shell" id="staff-main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}


