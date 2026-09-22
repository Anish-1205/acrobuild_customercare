import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { getCSApiSettings, saveCSApiSettings } from "../lib/api";
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

  return <section className="cs-api-settings">
    {!embedded && <Link to="/admin/workspace">← Back to dashboard</Link>}
    <h1>CS API settings</h1>
    <p>Configure the property data connection. Saved settings take effect immediately and remain after a restart.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {loading ? <p role="status">Loading settings…</p> : !loaded ? <button onClick={() => void load()}>Retry</button> :
      <form onSubmit={event => void save(event)}>
        <fieldset disabled={saving}>
          <label htmlFor="cs-base-url">Base URL</label>
          <input id="cs-base-url" type="url" required maxLength={2048} value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="https://api.example.com" />
          <label htmlFor="cs-company-id">Company ID</label>
          <input id="cs-company-id" type="number" required min={1} step={1} value={companyId} onChange={event => setCompanyId(event.target.value)} />
          <label htmlFor="cs-api-key">API key</label>
          <input id="cs-api-key" type="password" autoComplete="new-password" required={!configured} maxLength={4096} value={apiKey} onChange={event => setApiKey(event.target.value)} aria-describedby="cs-key-help" />
          <p id="cs-key-help">{configured ? "A key is configured. Leave blank to keep it, or enter a replacement." : "Enter the API key for this connection."}</p>
          <button type="submit">{saving ? "Saving…" : "Save settings"}</button>
        </fieldset>
      </form>}
  </section>;
}
