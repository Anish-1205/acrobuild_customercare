import { useState } from "react";
import { Link } from "react-router-dom";
import { AcrobuildLogo } from "./AcrobuildLogo";

type PublicHeaderProps = {
  workspaceLabel: string;
  workspaceLink: string;
};

const publicNavigation = [
  { className: "help-center-header-home", label: "Home", to: "/home" },
  { label: "Popular questions", to: "/home#popular-questions" },
  { label: "All articles", to: "/home#more-information" },
  { label: "Get support", to: "/home#get-support" }
];

export function PublicHeader({ workspaceLabel, workspaceLink }: PublicHeaderProps) {
  const [isNavigationOpen, setIsNavigationOpen] = useState(false);

  return (
    <header className="help-center-header">
      <div className="help-center-shell help-center-header-inner">
        <Link aria-label="Acrobuild home" className="help-center-header-brand" to="/home">
          <AcrobuildLogo subtitle="Project support desk" />
        </Link>

        <button
          aria-controls="public-navigation"
          aria-expanded={isNavigationOpen}
          className="help-center-nav-toggle"
          onClick={() => setIsNavigationOpen((current) => !current)}
          type="button"
        >
          <span aria-hidden="true" className="help-center-nav-toggle-icon">
            <i />
            <i />
            <i />
          </span>
          Menu
        </button>

        <nav
          aria-label="Help center sections"
          className={`help-center-header-nav${isNavigationOpen ? " is-open" : ""}`}
          id="public-navigation"
        >
          {publicNavigation.map((item) => (
            <Link
              className={item.className}
              key={item.to}
              onClick={() => setIsNavigationOpen(false)}
              to={item.to}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <Link className="help-center-header-link" to={workspaceLink}>
          {workspaceLabel}
        </Link>
      </div>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="help-center-footer">
      <div className="help-center-shell help-center-footer-inner">
        <Link className="help-center-footer-brand" to="/home">
          <AcrobuildLogo className="acrobuild-logo-compact" subtitle="Buyer & homeowner support" />
        </Link>
        <nav aria-label="Footer" className="help-center-footer-links">
          <Link to="/home#more-information">All articles</Link>
          <Link to="/home#popular-questions">Popular questions</Link>
          <Link to="/home#get-support">Contact</Link>
        </nav>
      </div>
    </footer>
  );
}
