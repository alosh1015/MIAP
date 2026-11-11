import { useEffect, useState } from "react";
import { api, ApiError, type ModelEntry, type SettingsResponse, type SystemSettings } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { startTour } from "../components/ToolTour";
import { Icon, type IconName } from "../components/icons";
import { useTheme, type ThemePreference } from "../theme/ThemeContext";
import {
  Badge,
  Button,
  ErrorNote,
  Field,
  Input,
  Notice,
  Panel,
  PanelHeader,
  PageHeader,
  Select,
  Switch,
  Textarea,
  cx,
} from "../components/ui";

const CAPABILITY_LABELS: Record<string, string> = {
  can_see_identity: "See patient identity (own patients)",
  can_create_patient: "Create and link patients",
  can_review_findings: "Confirm or dismiss findings",
  can_run_batch: "Run batch analysis",
  can_export_dataset: "Export pseudonymised datasets",
  can_view_images: "View images and heatmaps",
  can_manage_users: "Manage users",
  can_approve_models: "Approve models",
  can_verify_audit: "Verify and export the audit chain",
  can_manage_retention: "Preview and run retention",
};

export function SettingsPage() {
  const { user } = useAuth();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load settings"));
  }, []);

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Settings"
        actions={
          <Button icon="info" onClick={startTour}>
            Take the tour
          </Button>
        }
      />
      <ErrorNote message={error} />
      {settings ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-6">
            <ProfilePanel settings={settings} />
            <AppearancePanel settings={settings} onSettings={setSettings} />
            <ViewerPanel settings={settings} onSettings={setSettings} />
            {user?.role === "researcher" ? (
              <ResearchDefaultsPanel settings={settings} onSettings={setSettings} />
            ) : null}
            {user?.role === "administrator" ? <SystemPanel /> : null}
          </div>
          <div className="space-y-4">
            <CapabilitiesPanel settings={settings} />
            <Panel className="p-5">
              <h2 className="text-base font-semibold text-ink">Notices</h2>
              <ul className="mt-2 space-y-2 text-sm text-muted">
                {settings.notices.map((notice) => (
                  <li key={notice} className="flex gap-2">
                    <Icon name="info" size={15} className="mt-0.5 shrink-0" />
                    {notice}
                  </li>
                ))}
              </ul>
            </Panel>
          </div>
        </div>
      ) : !error ? (
        <Panel className="p-8 text-sm text-muted">Loading settings…</Panel>
      ) : null}
    </div>
  );
}

function ProfilePanel({ settings }: { settings: SettingsResponse }) {
  return (
    <Panel>
      <PanelHeader title="Profile" />
      <dl className="grid gap-4 p-5 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted">Name</dt>
          <dd className="mt-0.5 text-sm text-ink">{settings.profile.display_name}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Email</dt>
          <dd className="mt-0.5 text-sm text-ink">{settings.profile.email}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Role</dt>
          <dd className="mt-0.5">
            <Badge tone="petrol">{settings.profile.role}</Badge>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Account ID</dt>
          <dd className="mt-0.5 font-mono text-xs text-muted">{settings.profile.id}</dd>
        </div>
      </dl>
    </Panel>
  );
}

function AppearancePanel({
  settings,
  onSettings,
}: {
  settings: SettingsResponse;
  onSettings: (settings: SettingsResponse) => void;
}) {
  const { theme, setTheme } = useTheme();
  const [busy, setBusy] = useState(false);

  async function choose(next: ThemePreference) {
    setTheme(next);
    setBusy(true);
    try {
      onSettings(await api.updateSettings({ theme: next }));
    } catch {
      /* the local preference still applies */
    } finally {
      setBusy(false);
    }
  }

  const options: { id: ThemePreference; label: string; icon: IconName }[] = [
    { id: "light", label: "Light", icon: "sun" },
    { id: "dark", label: "Dark", icon: "moon" },
    { id: "system", label: "System", icon: "monitor" },
  ];

  return (
    <Panel>
      <PanelHeader title="Appearance" />
      <div className="p-5">
        <div className="grid gap-1 sm:grid-cols-3" role="radiogroup" aria-label="Theme">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={theme === option.id}
              disabled={busy}
              onClick={() => choose(option.id)}
              className={cx(
                "flex items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition-colors duration-150 ease-out",
                theme === option.id
                  ? "bg-surface-2 font-medium text-ink"
                  : "text-muted hover:bg-surface-2/60 hover:text-ink",
              )}
            >
              <span
                aria-hidden="true"
                className={cx(
                  "h-1.5 w-1.5 shrink-0 rounded-full",
                  theme === option.id ? "bg-petrol" : "bg-rule-strong",
                )}
              />
              <Icon name={option.icon} size={17} />
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function ViewerPanel({
  settings,
  onSettings,
}: {
  settings: SettingsResponse;
  onSettings: (settings: SettingsResponse) => void;
}) {
  const [opacity, setOpacity] = useState(settings.preferences.viewer_overlay_opacity);
  const [split, setSplit] = useState(settings.preferences.viewer_split);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onSettings(await api.updateSettings({ viewer_overlay_opacity: opacity, viewer_split: split }));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not save preferences");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <PanelHeader title="Viewer defaults" />
      <div className="space-y-4 p-5">
        <div>
          <div className="flex items-center justify-between">
            <label htmlFor="overlay-opacity" className="text-sm font-medium text-ink">
              Overlay opacity
            </label>
            <span className="font-mono text-xs text-muted">{Math.round(opacity * 100)}%</span>
          </div>
          <input
            id="overlay-opacity"
            type="range"
            min={0.2}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(event) => setOpacity(Number(event.target.value))}
            className="mt-2 w-full accent-[var(--petrol)]"
          />
        </div>
        <Switch
          checked={split}
          onChange={setSplit}
          label="Start with the before/after split"
        />
        <ErrorNote message={error} />
        <div className="flex items-center justify-end gap-2">
          {saved ? <span className="text-xs text-petrol">Saved</span> : null}
          <Button variant="primary" loading={busy} onClick={save}>
            Save viewer defaults
          </Button>
        </div>
      </div>
    </Panel>
  );
}

function ResearchDefaultsPanel({
  settings,
  onSettings,
}: {
  settings: SettingsResponse;
  onSettings: (settings: SettingsResponse) => void;
}) {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [model, setModel] = useState(settings.preferences.default_model ?? "");
  const [format, setFormat] = useState(settings.preferences.export_format);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listModels()
      .then((entries) => setModels(entries.filter((entry) => entry.state === "approved")))
      .catch(() => undefined);
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onSettings(
        await api.updateSettings({ default_model: model || null, export_format: format as "csv" | "json" }),
      );
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not save preferences");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <PanelHeader title="Research defaults" />
      <div className="grid gap-4 p-5 sm:grid-cols-2">
        <Field label="Default model">
          <Select value={model} onChange={(event) => setModel(event.target.value)}>
            <option value="">Auto-select for image</option>
            {models.map((entry) => (
              <option key={`${entry.model_id}-${entry.version}`} value={entry.model_id}>
                {entry.model_id} · {entry.version}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Export format">
          <Select value={format} onChange={(event) => setFormat(event.target.value as "csv" | "json")}>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </Select>
        </Field>
        <div className="sm:col-span-2">
          <ErrorNote message={error} />
          <div className="flex items-center justify-end gap-2">
            {saved ? <span className="text-xs text-petrol">Saved</span> : null}
            <Button variant="primary" loading={busy} onClick={save}>
              Save research defaults
            </Button>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function SystemPanel() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSystemSettings()
      .then(setSettings)
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load system settings"));
  }, []);

  async function save() {
    if (!settings) return;
    setBusy(true);
    setError(null);
    try {
      setSettings(await api.updateSystemSettings(settings));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not save system settings");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <PanelHeader title="System settings" />
      {!settings ? (
        <div className="p-5 text-sm text-muted">{error ?? "Loading…"}</div>
      ) : (
        <div className="space-y-4 p-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Retention default (days)">
              <Input
                type="number"
                min={1}
                max={3650}
                value={settings.retention_default_days}
                onChange={(event) =>
                  setSettings({ ...settings, retention_default_days: Number(event.target.value) })
                }
              />
            </Field>
            <Field label="Export row cap">
              <Input
                type="number"
                min={1}
                max={100000}
                value={settings.export_row_cap}
                onChange={(event) => setSettings({ ...settings, export_row_cap: Number(event.target.value) })}
              />
            </Field>
            <Field label="Max batch images">
              <Input
                type="number"
                min={1}
                max={500}
                value={settings.max_batch_images}
                onChange={(event) => setSettings({ ...settings, max_batch_images: Number(event.target.value) })}
              />
            </Field>
          </div>
          <Field label="TB notice shown to clinicians">
            <Textarea
              value={settings.tb_notice}
              onChange={(event) => setSettings({ ...settings, tb_notice: event.target.value })}
            />
          </Field>
          <ErrorNote message={error} />
          <div className="flex items-center justify-end gap-2">
            {saved ? <span className="text-xs text-petrol">Saved</span> : null}
            <Button variant="primary" loading={busy} onClick={save}>
              Save system settings
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}

function CapabilitiesPanel({ settings }: { settings: SettingsResponse }) {
  return (
    <Panel>
      <PanelHeader title="What your role can see" />
      <ul className="divide-y divide-rule">
        {Object.entries(CAPABILITY_LABELS).map(([key, label]) => {
          const allowed = Boolean(settings.capabilities[key]);
          return (
            <li key={key} className="flex items-center gap-2 px-4 py-2.5 text-sm">
              <Icon
                name={allowed ? "check" : "close"}
                size={15}
                className={allowed ? "text-petrol" : "text-muted/60"}
              />
              <span className={allowed ? "text-ink" : "text-muted"}>{label}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
