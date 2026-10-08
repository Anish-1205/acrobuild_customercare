import { useEffect, useState } from "react";
import {
  getBusinessHoursProfiles,
  updateBusinessHoursProfile
} from "../lib/api";
import type { BusinessHoursProfile, BusinessHoursRange } from "../types";
import { StaffPageHeader } from "../components/StaffPageHeader";

const dayOptions = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday"
];

const timeOptions = Array.from({ length: 24 * 2 }, (_, index) => {
  const hours = `${Math.floor(index / 2)}`.padStart(2, "0");
  const minutes = index % 2 === 0 ? "00" : "30";
  return `${hours}:${minutes}`;
});

const timezoneOptions: string[] =
  typeof Intl !== "undefined" &&
  typeof (Intl as any).supportedValuesOf === "function"
    ? (Intl as any).supportedValuesOf("timeZone")
    : [
        "UTC",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Asia/Kolkata",
        "Asia/Tokyo",
        "Asia/Singapore"
      ];

type BusinessHoursPageProps = {
  embedded?: boolean;
};

function cloneProfile(profile: BusinessHoursProfile): BusinessHoursProfile {
  return {
    ...profile,
    ranges: profile.ranges.map((range) => ({ ...range }))
  };
}

export function BusinessHoursPage({ embedded = false }: BusinessHoursPageProps) {
  const [profiles, setProfiles] = useState<BusinessHoursProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [editor, setEditor] = useState<BusinessHoursProfile | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadProfiles(preferredProfileId?: number | null) {
    const profileResponse = await getBusinessHoursProfiles();
    const nextProfiles = profileResponse.profiles;
    setProfiles(nextProfiles);

    if (!nextProfiles.length) {
      setSelectedProfileId(null);
      setEditor(null);
      return;
    }

    const resolvedProfile =
      nextProfiles.find((profile) => profile.id === preferredProfileId) ??
      nextProfiles.find((profile) => Number(profile.is_default) === 1) ??
      nextProfiles[0];

    setSelectedProfileId(resolvedProfile.id);
    setEditor(cloneProfile(resolvedProfile));
  }

  useEffect(() => {
    void loadProfiles()
      .catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : "Unable to load business hours.");
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedProfileId) {
      return;
    }

    const activeProfile = profiles.find((profile) => profile.id === selectedProfileId);

    if (activeProfile) {
      setEditor(cloneProfile(activeProfile));
    }
  }, [profiles, selectedProfileId]);

  function updateRange(index: number, field: keyof BusinessHoursRange, value: string) {
    if (!editor) {
      return;
    }

    const nextRanges = editor.ranges.map((range, rangeIndex) =>
      rangeIndex === index ? { ...range, [field]: value } : range
    );

    setEditor({
      ...editor,
      ranges: nextRanges
    });
  }

  async function handleSave() {
    if (!editor) {
      return;
    }

    try {
      setIsSaving(true);
      setError("");
      setNotice("");
      await updateBusinessHoursProfile(editor);
      await loadProfiles(editor.id);
      setNotice("Business hours saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save business hours.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="stack-page">
      <StaffPageHeader
        description="Edit the selected persisted schedule profile, its timezone, and its existing coverage ranges."
        eyebrow={embedded ? "Coverage configuration" : "Coverage workspace"}
        title="Open Hours"
      />

      <div aria-live="polite" aria-atomic="true">
        {isLoading ? <div className="phase6-status" role="status">Loading open hours...</div> : null}
        {error ? <div className="banner-error" role="alert">{error}</div> : null}
        {notice ? <div className="banner-success" role="status">{notice}</div> : null}
      </div>

      <section className="plain-card workspace-detail-shell business-hours-compact-shell">
        <div className="workspace-detail-topbar">
          <div>
            <div className="workspace-detail-kicker">Coverage setup</div>
            <div className="section-title">Edit schedule</div>
            <div className="section-copy">The extra schedule directory and custom profile list have been removed to keep this page focused.</div>
          </div>

          <div className="workspace-detail-actions">
            <button
              className="primary-button"
              disabled={isSaving || !editor}
              onClick={() => void handleSave()}
              type="button"
            >
              Save changes
            </button>
          </div>
        </div>

        {editor ? (
          <>
            <div className="editor-grid">
              <label className="field-block">
                <span>Schedule profile</span>
                <select
                  className="field-input"
                  onChange={(event) => setSelectedProfileId(Number(event.target.value))}
                  value={selectedProfileId ?? ""}
                >
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-block">
                <span>Timezone</span>
                <select
                  className="field-input"
                  onChange={(event) =>
                    setEditor({
                      ...editor,
                      timezone: event.target.value
                    })
                  }
                  value={editor.timezone || timezoneOptions[0]}
                >
                  {timezoneOptions.map((timezone) => (
                    <option key={timezone} value={timezone}>
                      {timezone}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="workspace-detail-preview">
              <div className="toolbar-row wrap">
                <span className="soft-pill">{Number(editor.is_default) === 1 ? "Default profile" : "Custom profile"}</span>
                <span className="section-copy">{editor.summary}</span>
              </div>
            </div>

            <label className="field-block">
              <span>Description</span>
              <textarea
                className="field-textarea short"
                onChange={(event) =>
                  setEditor({
                    ...editor,
                    description: event.target.value
                  })
                }
                rows={3}
                value={editor.description}
              />
            </label>

            <div className="range-stack">
              {editor.ranges.map((range, index) => (
                <div className="range-row" key={`${range.day_name}-${index}`}>
                  <select
                    aria-label={`Day for range ${index + 1}`}
                    className="field-input"
                    onChange={(event) => updateRange(index, "day_name", event.target.value)}
                    value={range.day_name}
                  >
                    {dayOptions.map((day) => (
                      <option key={day} value={day}>
                        {day}
                      </option>
                    ))}
                  </select>

                  <select
                    aria-label={`Start time for range ${index + 1}`}
                    className="field-input"
                    onChange={(event) => updateRange(index, "start_time", event.target.value)}
                    value={range.start_time}
                  >
                    {timeOptions.map((timeValue) => (
                      <option key={timeValue} value={timeValue}>
                        {timeValue}
                      </option>
                    ))}
                  </select>

                  <select
                    aria-label={`End time for range ${index + 1}`}
                    className="field-input"
                    onChange={(event) => updateRange(index, "end_time", event.target.value)}
                    value={range.end_time}
                  >
                    {timeOptions.map((timeValue) => (
                      <option key={timeValue} value={timeValue}>
                        {timeValue}
                      </option>
                    ))}
                  </select>

                  <button
                    className="mini-danger"
                    disabled={editor.ranges.length <= 1 || isSaving}
                    onClick={() =>
                      setEditor({
                        ...editor,
                        ranges: editor.ranges.filter((_, rangeIndex) => rangeIndex !== index)
                      })
                    }
                    type="button"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>

            <div className="action-row">
              <button
                className="ghost-button"
                disabled={isSaving}
                onClick={() =>
                  setEditor({
                    ...editor,
                    ranges: [
                      ...editor.ranges,
                      {
                        day_name: "Monday",
                        end_time: "17:00",
                        start_time: "09:00"
                      }
                    ]
                  })
                }
                type="button"
              >
                Add time range
              </button>
            </div>
          </>
        ) : (
          <div className="empty-card">No business-hours profile is available yet.</div>
        )}
      </section>
    </div>
  );
}
