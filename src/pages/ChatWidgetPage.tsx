import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  buildInstallSnippet,
  loadWidgetConfig,
  saveWidgetConfig
} from "../lib/widgetConfig";

type ChatWidgetPageProps = {
  embedded?: boolean;
};

const installSteps = [
  "Open the website source and find the closing </body> tag.",
  "Paste the widget snippet above the closing </body> tag.",
  "Publish the updated page and verify the launcher appears."
];

export function ChatWidgetPage({ embedded = false }: ChatWidgetPageProps) {
  const initialWidgetConfig = useMemo(() => loadWidgetConfig(), []);
  const [chatTitle, setChatTitle] = useState(initialWidgetConfig.chatTitle);
  const [introMessage, setIntroMessage] = useState(initialWidgetConfig.introMessage);
  const [accentColor, setAccentColor] = useState(initialWidgetConfig.accentColor);
  const [fontFamily, setFontFamily] = useState(initialWidgetConfig.fontFamily);
  const [launcherWidth, setLauncherWidth] = useState(initialWidgetConfig.launcherWidth);
  const [logoUrl, setLogoUrl] = useState(initialWidgetConfig.logoUrl);
  const [aiResponsesEnabled, setAiResponsesEnabled] = useState(initialWidgetConfig.aiResponsesEnabled);
  const [widgetWidth, setWidgetWidth] = useState(initialWidgetConfig.widgetWidth);
  const [assistantName, setAssistantName] = useState(initialWidgetConfig.assistantName);
  const [widgetKey, setWidgetKey] = useState(initialWidgetConfig.widgetKey);
  const [articleSuggestionsEnabled, setArticleSuggestionsEnabled] = useState(initialWidgetConfig.articleSuggestionsEnabled);
  const [copyState, setCopyState] = useState("");
  const normalizedLogoUrl = logoUrl.trim();
  const assistantInitial = assistantName.trim().charAt(0).toUpperCase() || "S";

  const installSnippet = useMemo(
    () => buildInstallSnippet(widgetKey, accentColor, widgetWidth, normalizedLogoUrl),
    [accentColor, normalizedLogoUrl, widgetKey, widgetWidth]
  );

  useEffect(() => {
    saveWidgetConfig({
      accentColor,
      aiResponsesEnabled,
      articleSuggestionsEnabled,
      assistantName,
      chatTitle,
      fontFamily,
      introMessage,
      launcherLabel: initialWidgetConfig.launcherLabel,
      launcherWidth,
      logoUrl,
      widgetKey,
      widgetWidth
    });
  }, [
    accentColor,
    aiResponsesEnabled,
    articleSuggestionsEnabled,
    assistantName,
    chatTitle,
    fontFamily,
    introMessage,
    initialWidgetConfig.launcherLabel,
    launcherWidth,
    logoUrl,
    widgetKey,
    widgetWidth
  ]);

  async function handleCopySnippet() {
    try {
      await navigator.clipboard.writeText(installSnippet);
      setCopyState("Installation script copied.");
      window.setTimeout(() => setCopyState(""), 1800);
    } catch {
      setCopyState("Clipboard permission blocked. Copy manually from the code block.");
    }
  }

  return (
    <div className="stack-page">
      {!embedded ? (
        <section className="hero-card compact">
          <div className="hero-kicker">Chat Experience</div>
          <h2>Chat Widget</h2>
          <p>
            Configure the public support widget, tune the chat width, and install the
            launcher snippet on storefront pages.
          </p>
        </section>
      ) : null}

      {copyState ? <div className="banner-success">{copyState}</div> : null}

      <div className="widget-layout">
        <div className="widget-main">
          <section className="plain-card">
            <div className="toolbar-row spread wrap">
              <div>
                <div className="section-title">Appearance</div>
                <div className="section-copy">
                  Tune the launcher, widget width, and first impression for the support assistant.
                </div>
              </div>

              <span className="soft-pill">Live preview updates instantly</span>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Chat title</span>
                <input className="field-input" onChange={(event) => setChatTitle(event.target.value)} value={chatTitle} />
              </label>

              <label className="field-block">
                <span>Assistant name</span>
                <input
                  className="field-input"
                  onChange={(event) => setAssistantName(event.target.value)}
                  value={assistantName}
                />
              </label>
            </div>

            <label className="field-block">
              <span>Intro message</span>
              <textarea
                className="field-textarea short"
                onChange={(event) => setIntroMessage(event.target.value)}
                rows={4}
                value={introMessage}
              />
            </label>

            <div className="editor-grid">
              <label className="field-block">
                <span>Launcher logo URL</span>
                <input
                  className="field-input widget-control"
                  onChange={(event) => setLogoUrl(event.target.value)}
                  placeholder="https://your-site.com/acrobuild-logo.png"
                  value={logoUrl}
                />
                <div className="widget-preview-caption">
                  Add a public image URL to use the same logo in the preview, help-center widget, and embed snippet.
                </div>
              </label>

              <label className="field-block">
                <span>Font</span>
                <select className="field-input widget-control widget-control-select" onChange={(event) => setFontFamily(event.target.value)} value={fontFamily}>
                  <option value="Georgia">Georgia</option>
                  <option value="Trebuchet MS">Trebuchet MS</option>
                  <option value="Segoe UI">Segoe UI</option>
                  <option value="Verdana">Verdana</option>
                  <option value="Aptos">Aptos</option>
                </select>
              </label>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Widget key</span>
                <input className="field-input" onChange={(event) => setWidgetKey(event.target.value)} value={widgetKey} />
              </label>

              <div className="field-block">
                <span>Launcher style</span>
                <div className="widget-preview-caption">
                  The launcher now uses a compact message icon instead of a text pill.
                </div>
              </div>
            </div>

            <div className="editor-grid">
              <label className="field-block">
                <span>Chat width: {widgetWidth}px</span>
                <input
                  className="widget-range"
                  max="380"
                  min="320"
                  onChange={(event) => setWidgetWidth(Number(event.target.value))}
                  type="range"
                  value={widgetWidth}
                />
              </label>

              <label className="field-block">
                <span>Launcher size: {launcherWidth}px</span>
                <input
                  className="widget-range"
                  max="72"
                  min="52"
                  onChange={(event) => setLauncherWidth(Number(event.target.value))}
                  type="range"
                  value={launcherWidth}
                />
              </label>
            </div>
          </section>

          <section className="plain-card">
            <div className="section-title">Reply Behavior</div>
            <div className="section-copy">
              The widget uses Acrobuild support knowledge behind the scenes, then asks for quick feedback before handing the conversation to the team when needed.
            </div>

            <div className="selection-list widget-feature-list">
              <label className="selection-row">
                <input
                  checked={aiResponsesEnabled}
                  onChange={(event) => setAiResponsesEnabled(event.target.checked)}
                  type="checkbox"
                />
                <span>
                  <strong>AI answers in chat</strong>
                  <small>The widget answers directly from published articles and uploaded training knowledge before offering ticket handoff.</small>
                </span>
              </label>

              <label className="selection-row">
                <input checked disabled type="checkbox" />
                <span>
                  <strong>Knowledge stays behind the answer</strong>
                  <small>Published support guidance shapes the reply quietly in the background instead of dropping full article cards into the chat.</small>
                </span>
              </label>

              <label className="selection-row">
                <input
                  checked={articleSuggestionsEnabled}
                  onChange={(event) => setArticleSuggestionsEnabled(event.target.checked)}
                  type="checkbox"
                />
                <span>
                  <strong>Feedback after AI replies</strong>
                  <small>Customers can rate the answer with thumbs up or thumbs down so the next message reacts to their review.</small>
                </span>
              </label>
            </div>
          </section>

          <section className="plain-card">
            <div className="toolbar-row spread wrap">
              <div>
                <div className="section-title">Manual Installation</div>
                <div className="section-copy">
                  Install the support widget on any website by placing one script before the closing body tag.
                </div>
              </div>

              <button className="ghost-button" onClick={() => void handleCopySnippet()} type="button">
                Copy Script
              </button>
            </div>

            <div className="selection-list widget-install-steps">
              {installSteps.map((step, index) => (
                <div className="selection-row" key={step}>
                  <span className="widget-step-index">{index + 1}</span>
                  <span>
                    <strong>{step}</strong>
                  </span>
                </div>
              ))}
            </div>

            <div className="widget-code-shell">
              <pre>{installSnippet}</pre>
            </div>
          </section>
        </div>

        <div className="widget-side">
          <section className="plain-card widget-preview-panel">
            <div className="toolbar-row spread wrap">
              <div>
                <div className="section-title">Widget Preview</div>
                <div className="section-copy">Launcher and chat width mirror the values configured on the left.</div>
              </div>

              <Link className="ghost-button button-link" to="/home">
                Open test home
              </Link>
            </div>

            <div className="widget-device">
              <div className="widget-preview-window" style={{ width: `${widgetWidth}px`, fontFamily }}>
                <div className="widget-preview-head" style={{ backgroundColor: accentColor }}>
                  {normalizedLogoUrl ? (
                    <span className="widget-preview-brand">
                      <img alt="" className="widget-preview-brand-logo" src={normalizedLogoUrl} />
                    </span>
                  ) : null}
                  <strong>{assistantName}</strong>
                </div>

                <div className="widget-preview-body">
                  <div className="widget-preview-agent">{chatTitle}</div>
                  <div className="widget-preview-copy">{introMessage}</div>

                  <div className="widget-preview-thread">
                    <div className="widget-preview-date">June 8</div>

                    <div className="widget-preview-row customer">
                      <div
                        className="widget-preview-chat-bubble customer"
                        style={{
                          backgroundColor: accentColor,
                          borderColor: accentColor
                        }}
                      >
                        I am considering a demo or a trial
                      </div>
                    </div>

                    <div className="widget-preview-row bot">
                      <span className={`widget-preview-chat-avatar${normalizedLogoUrl ? " has-logo" : ""}`}>
                        {normalizedLogoUrl ? (
                          <img alt="" className="widget-preview-chat-avatar-image" src={normalizedLogoUrl} />
                        ) : (
                          assistantInitial
                        )}
                      </span>
                      <div className="widget-preview-chat-stack">
                        <div className="widget-preview-chat-author">Bot</div>
                        <div className="widget-preview-chat-bubble automated">
                          {aiResponsesEnabled
                            ? "I checked the latest Acrobuild support knowledge and can help with that right here."
                            : "Happy to help! We&apos;ll connect you with a team member."}
                        </div>
                        {articleSuggestionsEnabled ? (
                          <div className="widget-preview-feedback">
                            <div className="widget-preview-feedback-label">Was this helpful?</div>
                            <div className="widget-preview-feedback-actions">
                              <button aria-label="Helpful answer" className="widget-preview-feedback-button positive" type="button">
                                <svg aria-hidden="true" className="widget-preview-feedback-icon" viewBox="0 0 24 24">
                                  <path d="M9.5 10.25V20H6.25A2.25 2.25 0 0 1 4 17.75v-5.25a2.25 2.25 0 0 1 2.25-2.25H9.5Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
                                  <path d="M9.5 10.25 13 4.75c.31-.49.86-.79 1.44-.79h.06c.83 0 1.5.67 1.5 1.5v3.29h2.16A1.84 1.84 0 0 1 20 10.59l-1.11 7.2A2.5 2.5 0 0 1 16.42 20H9.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                                </svg>
                              </button>
                              <button aria-label="Not helpful" className="widget-preview-feedback-button negative" type="button">
                                <svg aria-hidden="true" className="widget-preview-feedback-icon" viewBox="0 0 24 24">
                                  <path d="M9.5 13.75V4H6.25A2.25 2.25 0 0 0 4 6.25v5.25a2.25 2.25 0 0 0 2.25 2.25H9.5Z" fill="none" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
                                  <path d="m9.5 13.75 3.5 5.5c.31.49.86.79 1.44.79h.06c.83 0 1.5-.67 1.5-1.5v-3.29h2.16A1.84 1.84 0 0 0 20 13.41l-1.11-7.2A2.5 2.5 0 0 0 16.42 4H9.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                                </svg>
                              </button>
                            </div>
                          </div>
                        ) : null}
                        <div className="widget-preview-chat-note">Automated</div>
                      </div>
                    </div>

                    <div className="widget-preview-row customer">
                      <div
                        className="widget-preview-chat-bubble customer"
                        style={{
                          backgroundColor: accentColor,
                          borderColor: accentColor
                        }}
                      >
                        Yes, thank you
                      </div>
                    </div>

                    <div className="widget-preview-row bot">
                      <span className={`widget-preview-chat-avatar${normalizedLogoUrl ? " has-logo" : ""}`}>
                        {normalizedLogoUrl ? (
                          <img alt="" className="widget-preview-chat-avatar-image" src={normalizedLogoUrl} />
                        ) : (
                          assistantInitial
                        )}
                      </span>
                      <div className="widget-preview-chat-stack">
                        <div className="widget-preview-chat-author">Bot</div>
                        <div className="widget-preview-chat-bubble automated">
                          Thanks for the thumbs up. Glad that helped.
                        </div>
                        <div className="widget-preview-chat-note">Automated</div>
                      </div>
                    </div>


                    <div className="widget-preview-home-link">Back To Home</div>
                  </div>
                </div>
              </div>

              <button
                aria-label={initialWidgetConfig.launcherLabel}
                className={`widget-launcher-preview icon-only${normalizedLogoUrl ? " has-logo" : ""}`}
                style={{
                  height: `${launcherWidth}px`,
                  width: `${launcherWidth}px`,
                  backgroundColor: normalizedLogoUrl ? "#ffffff" : accentColor
                }}
                type="button"
              >
                {normalizedLogoUrl ? (
                  <img alt="" className="widget-launcher-preview-logo" src={normalizedLogoUrl} />
                ) : (
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <path
                      d="M4 5.5C4 4.12 5.12 3 6.5 3h11C18.88 3 20 4.12 20 5.5v7c0 1.38-1.12 2.5-2.5 2.5H10l-4.2 3.6c-.46.39-1.12.06-1.12-.54V15.7A2.48 2.48 0 0 1 4 13.5v-8Z"
                      fill="currentColor"
                    />
                  </svg>
                )}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
