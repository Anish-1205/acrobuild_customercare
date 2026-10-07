import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { getCSApiSettings, saveCSApiSettings } from "../lib/api";
import { StaffPageHeader } from "../components/StaffPageHeader";
import "./CSApiSettingsPage.css";

export function CSApiSettingsPage({ embedded = false }: { embedded?: boolean }) {
  const [baseUrl, setBaseUrl] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setLoading(true); setError("");
    try {
      const settings = await getCSApiSettings();
      setBaseUrl(settings.base_url); setCompanyId(settings.company_id);
      setConfigured(settings.api_key_configured); setLoaded(true);
    } catch {
      setError("Could not load CS API settings. Please try again.");
    } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  async function save(event: FormEvent) {
    event.preventDefault(); setError(""); setNotice("");
    const id = Number(companyId);
    if (!Number.isSafeInteger(id) || id <= 0) {
      setError("Company ID must be a positive whole number."); return;
    }
    setSaving(true);
    try {
      const settings = await saveCSApiSettings({ base_url: baseUrl.trim(), company_id: id, api_key: apiKey.trim() });
      setBaseUrl(settings.base_url); setCompanyId(settings.company_id);
      setConfigured(settings.api_key_configured); setApiKey("");
      setNotice("Settings saved. New CS API requests will use this configuration.");
    } catch {
      setError("Could not save settings. Check the URL, company ID, and API key, then try again.");
    } finally { setSaving(false); }
  }

  return <div className="stack-page cs-api-settings-page">
    <StaffPageHeader
      description="Configure the persisted property-data connection. The saved API key is write-only and is never returned to this page."
      eyebrow={embedded ? "Secure connection" : "Admin settings"}
      title="CS API Settings"
    />
    {!embedded && <Link className="ghost-button button-link cs-api-back-link" to="/admin/workspace">Back to workspace</Link>}
    <div aria-live="polite" aria-atomic="true">
      {error && <div className="phase6-status" role="alert">{error}</div>}
      {notice && <div className="phase6-status" role="status">{notice}</div>}
    </div>
    {loading ? <div className="phase6-status" role="status">Loading settings...</div> : !loaded ? (
      <button className="primary-button" onClick={() => void load()} type="button">Retry</button>
    ) : (
      <form className="plain-card cs-api-settings" onSubmit={event => void save(event)}>
        <fieldset disabled={saving}>
          <legend>Property data connection</legend>
          <label className="field-block" htmlFor="cs-base-url">
            <span>Base URL</span>
            <input className="field-input" id="cs-base-url" type="url" required maxLength={2048} value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="https://api.example.com" />
          </label>
          <label className="field-block" htmlFor="cs-company-id">
            <span>Company ID</span>
            <input className="field-input" id="cs-company-id" type="number" required min={1} step={1} value={companyId} onChange={event => setCompanyId(event.target.value)} />
          </label>
          <label className="field-block" htmlFor="cs-api-key">
            <span>API key</span>
            <input className="field-input" id="cs-api-key" type="password" autoComplete="new-password" required={!configured} maxLength={4096} value={apiKey} onChange={event => setApiKey(event.target.value)} aria-describedby="cs-key-help" />
          </label>
          <p className="cs-api-key-help" id="cs-key-help">{configured ? "A key is configured. Leave this field blank to keep it, or enter a replacement." : "Enter the API key for this connection."}</p>
          <button className="primary-button" type="submit">{saving ? "Saving..." : "Save settings"}</button>
        </fieldset>
      </form>
    )}
  </div>;
}
