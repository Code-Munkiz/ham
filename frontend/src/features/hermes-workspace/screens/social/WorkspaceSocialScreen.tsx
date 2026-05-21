import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  socialAdapter,
  type GoHamSocialProfile,
  type SocialAutonomyStatus,
  type SocialAutonomyTickResult,
  type SocialAutonomyTickSummary,
} from "../../adapters/socialAdapter";
import {
  WorkspaceSurfaceHeader,
  WorkspaceSurfaceStateCard,
} from "../../components/workspaceSurfaceChrome";

type LimitsForm = {
  postsPerDay: number;
  repliesPerDay: number;
};

const EXAMPLE_GOALS = [
  "grow awareness",
  "announce updates",
  "engage community",
  "educate users",
  "launch campaign",
] as const;

const SAFETY_BOUNDARIES = [
  "no spam",
  "no mass tagging",
  "no financial promises",
  "no credential requests",
  "emergency stop available",
] as const;

function fallbackProfile(): GoHamSocialProfile {
  const now = new Date().toISOString();
  return {
    profile_id: "social-ui-default",
    workspace_id: null,
    project_id: null,
    status: "draft",
    goal: "grow awareness",
    persona_id: "ham-canonical",
    channels: {
      x: { enabled: true, available: true },
      telegram: { enabled: false, available: true },
      discord: { enabled: false, available: false },
    },
    actions_allowed_per_channel: {
      x: ["reply", "broadcast"],
      telegram: ["message", "activity", "reply"],
      discord: [],
    },
    daily_caps: { x: 3, telegram: 5, discord: 0 },
    cadence: "daily",
    quiet_hours: null,
    forbidden_topics: [],
    safety_rules: [...SAFETY_BOUNDARIES],
    learning_enabled: true,
    emergency_stop: false,
    last_run_at: null,
    next_run_at: null,
    last_tick_summary: null,
    created_at: now,
    updated_at: now,
  };
}

function normalizeProfile(profile: GoHamSocialProfile | null): GoHamSocialProfile {
  if (!isUsableProfile(profile)) {
    return fallbackProfile();
  }
  const base = fallbackProfile();
  return {
    ...base,
    ...profile,
    channels: {
      ...base.channels,
      ...(profile.channels ?? {}),
      discord: { enabled: false, available: false },
    },
    actions_allowed_per_channel: {
      ...base.actions_allowed_per_channel,
      ...(profile.actions_allowed_per_channel ?? {}),
    },
    daily_caps: { ...base.daily_caps, ...(profile.daily_caps ?? {}) },
    safety_rules: profile.safety_rules?.length ? profile.safety_rules : base.safety_rules,
  };
}

function isUsableProfile(profile: GoHamSocialProfile | null): profile is GoHamSocialProfile {
  return Boolean(
    profile &&
    ["draft", "running", "paused", "stopped"].includes(
      (profile as { status?: string }).status ?? "",
    ),
  );
}

function statusLabel(profile: GoHamSocialProfile): string {
  if (profile.emergency_stop) return "Emergency stopped";
  const labels: Record<SocialAutonomyStatus, string> = {
    draft: "Not launched",
    running: "Running",
    paused: "Paused",
    stopped: "Stopped",
  };
  return labels[profile.status];
}

function statusBadge(
  profile: GoHamSocialProfile,
  profileInvalid: boolean,
): { label: string; className: string } {
  if (profileInvalid) {
    return {
      label: "Unknown",
      className: "border-white/10 bg-white/[0.04] text-white/70",
    };
  }
  if (profile.emergency_stop) {
    return {
      label: "Stopped",
      className: "border-red-300/30 bg-red-500/10 text-red-100",
    };
  }
  if (profile.status === "running") {
    return {
      label: "Running",
      className: "border-emerald-300/30 bg-emerald-500/10 text-emerald-100",
    };
  }
  if (profile.status === "paused") {
    return {
      label: "Paused",
      className: "border-amber-300/30 bg-amber-500/10 text-amber-100",
    };
  }
  if (profile.status === "stopped") {
    return {
      label: "Stopped",
      className: "border-red-300/30 bg-red-500/10 text-red-100",
    };
  }
  return {
    label: "Unknown",
    className: "border-white/10 bg-white/[0.04] text-white/70",
  };
}

function channelBadge(profile: GoHamSocialProfile, channel: "x" | "telegram" | "discord"): string {
  if (channel === "discord") return "Not available";
  const cfg = profile.channels[channel];
  if (cfg?.enabled && cfg.available !== false) return "Available";
  if (cfg?.available === false) return "Not connected";
  return "Preview only";
}

function limitsFromProfile(profile: GoHamSocialProfile): LimitsForm {
  const postsPerDay = Number(profile.daily_caps.x ?? 0);
  const repliesPerDay = Number(profile.daily_caps.telegram ?? 0);
  return {
    postsPerDay,
    repliesPerDay,
  };
}

function redactPlainText(value: string | null | undefined): string {
  if (!value) return "HAM is still gathering enough signal to share a useful lesson.";
  const safe = value
    .split(/\r?\n/)
    .filter((line) => !/workspace_id|draft_id|record_id/i.test(line))
    .join("\n")
    .replace(/\{\"/g, "")
    .replace(/\":\[/g, ": ")
    .replace(/[{}[\]"]/g, "")
    .replace(new RegExp(["HAM_SOCIAL", "LIVE_APPLY_TOKEN"].join("_"), "g"), "operator credential")
    .replace(/policy_[a-z0-9_\-]+/gi, "safety signal")
    .trim();
  return safe || "HAM is still gathering enough signal to share a useful lesson.";
}

function formatTickTimestamp(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d{3}Z$/, " UTC")
    .replace(/Z$/, " UTC");
}

function pluralize(count: number, singular: string): string {
  return `${count} ${singular}${count === 1 ? "" : "s"}`;
}

function tickCountSummary(summary: SocialAutonomyTickSummary | SocialAutonomyTickResult): string {
  return `${pluralize(summary.actions_considered.length, "considered")}; ${pluralize(
    summary.actions_taken.length,
    "taken",
  )}`;
}

function formatActivity(profile: GoHamSocialProfile): string {
  const updated = profile.updated_at ? new Date(profile.updated_at) : null;
  const when = updated && !Number.isNaN(updated.getTime()) ? updated.toLocaleString() : "recently";
  if (profile.emergency_stop) {
    return `Activity paused by the emergency stop. Last profile update: ${when}.`;
  }
  if (profile.status === "running") {
    return `HAM is operating inside the configured limits. Last profile update: ${when}.`;
  }
  if (profile.status === "paused") {
    return `HAM is paused and waiting for you to resume. Last profile update: ${when}.`;
  }
  return `HAM is ready when you are. Last profile update: ${when}.`;
}

function Card({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-label={title}
      className={`rounded-2xl border border-white/10 bg-white/[0.035] p-4 shadow-sm ${className}`}
    >
      <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-white/60">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm text-white/70">
      <span>{label}</span>
      <input
        className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white outline-none focus:border-emerald-300/50"
        min={0}
        type="number"
        value={value}
        onChange={(event) => onChange(Math.max(0, Number(event.target.value) || 0))}
      />
    </label>
  );
}

function SocialStatusPanel({
  profile,
  profileInvalid,
}: {
  profile: GoHamSocialProfile;
  profileInvalid: boolean;
}) {
  const [previewResult, setPreviewResult] = React.useState<SocialAutonomyTickResult | null>(null);
  const [previewBusy, setPreviewBusy] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const badge = statusBadge(profile, profileInvalid);
  const lastTickTime = formatTickTimestamp(profile.last_tick_summary?.recorded_at);
  const nextRunTime = formatTickTimestamp(profile.next_run_at);
  const previewEnabled = !profileInvalid && profile.status === "running";

  const runPreview = async () => {
    if (!previewEnabled || previewBusy) return;
    setPreviewBusy(true);
    setPreviewError(null);
    setPreviewResult(null);
    try {
      const result = await socialAdapter.previewAutonomyTick({ dry_run: true });
      if (result.tick) {
        setPreviewResult(result.tick);
      } else {
        setPreviewError("Preview tick failed.");
      }
    } catch {
      setPreviewError("Preview tick failed.");
    } finally {
      setPreviewBusy(false);
    }
  };

  return (
    <Card title="Autonomy status">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <span
            role="status"
            aria-label={badge.label}
            className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold ${badge.className}`}
          >
            {badge.label}
          </span>
          <p className="mt-2 text-sm text-white/60">
            Dry-run preview of the next autonomous social tick.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => void runPreview()}
          disabled={!previewEnabled || previewBusy}
          aria-busy={previewBusy ? "true" : undefined}
        >
          {previewBusy ? "Previewing…" : "Preview tick"}
        </Button>
      </div>

      <dl className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.1em] text-white/45">
            Last tick
          </dt>
          <dd
            data-testid="social-status-last-tick"
            className="mt-1 break-words text-sm text-white/80"
          >
            {profile.last_tick_summary && lastTickTime ? (
              <>
                <span>{lastTickTime}</span>
                <span className="block text-xs text-white/55">
                  {tickCountSummary(profile.last_tick_summary)}
                </span>
              </>
            ) : (
              "—"
            )}
          </dd>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.1em] text-white/45">
            Next run
          </dt>
          <dd data-testid="social-status-next-run" className="mt-1 text-sm text-white/80">
            {nextRunTime ?? "—"}
          </dd>
        </div>
      </dl>

      {previewResult ? (
        <div
          aria-live="polite"
          className="mt-4 rounded-xl border border-emerald-300/15 bg-emerald-500/5 px-3 py-3 text-sm text-emerald-50/85"
        >
          <p className="font-medium text-emerald-50">Preview summary</p>
          <p className="mt-1">{tickCountSummary(previewResult)}</p>
          <p className="mt-1">Profile status: {previewResult.profile_status}</p>
          <p className="mt-1">
            Blocked reasons:{" "}
            {previewResult.blocked_reasons.length ? previewResult.blocked_reasons.join(", ") : "—"}
          </p>
          {previewResult.next_run_summary ? (
            <p className="mt-1">{previewResult.next_run_summary}</p>
          ) : null}
        </div>
      ) : null}

      {previewError ? (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-100"
        >
          {previewError}
        </p>
      ) : null}
    </Card>
  );
}

export function WorkspaceSocialScreen() {
  const [profile, setProfile] = React.useState<GoHamSocialProfile>(() => fallbackProfile());
  const [learningText, setLearningText] = React.useState<string>("");
  const [goalDraft, setGoalDraft] = React.useState<string>("grow awareness");
  const [limits, setLimits] = React.useState<LimitsForm>(() =>
    limitsFromProfile(fallbackProfile()),
  );
  const [loading, setLoading] = React.useState(true);
  const [busyAction, setBusyAction] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [profileInvalid, setProfileInvalid] = React.useState(false);
  const [writeToken, setWriteToken] = React.useState("");
  const [writesEnabled, setWritesEnabled] = React.useState(true);

  const applyProfile = React.useCallback((next: GoHamSocialProfile | null) => {
    const usable = isUsableProfile(next);
    const normalized = normalizeProfile(next);
    setProfile(normalized);
    setGoalDraft(normalized.goal);
    setLimits(limitsFromProfile(normalized));
    setProfileInvalid(!usable);
    return usable;
  }, []);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const [profileRes, hintsRes, writeStatusRes] = await Promise.all([
      socialAdapter.getAutonomyProfile(),
      socialAdapter.getLearningHints({ channel: "x", limit: 5 }),
      socialAdapter.getAutonomyWriteStatus(),
    ]);
    const usableProfile = applyProfile(profileRes.profile);
    setLearningText(redactPlainText(hintsRes.hints?.hints));
    if (writeStatusRes.status) {
      setWritesEnabled(writeStatusRes.status.writes_enabled);
    }
    const firstError = profileRes.error ?? hintsRes.error ?? writeStatusRes.error ?? null;
    if (!usableProfile) {
      setError("Social autonomy profile could not be loaded safely.");
    } else if (firstError) setError(firstError);
    setLoading(false);
  }, [applyProfile]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const runAction = async (
    label: string,
    action: () => Promise<{ profile: GoHamSocialProfile | null; error?: string }>,
  ) => {
    setBusyAction(label);
    setError(null);
    const result = await action();
    if (result.profile) applyProfile(result.profile);
    if (result.error) setError(result.error);
    setBusyAction(null);
  };

  const saveLimits = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await runAction("limits", () =>
      socialAdapter.updateAutonomyLimits(
        {
          daily_caps: {
            x: limits.postsPerDay,
            telegram: limits.repliesPerDay,
            discord: 0,
          },
        },
        writeToken,
      ),
    );
  };

  const writeTokenMissing = writeToken.trim().length === 0;
  const writeControlsDisabled = !writesEnabled || writeTokenMissing || busyAction !== null;
  const launchDisabled = profile.emergency_stop || profileInvalid || writeControlsDisabled;
  const totalDailyActions = limits.postsPerDay + limits.repliesPerDay;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4 overflow-y-auto p-3 text-white md:p-4">
      <WorkspaceSurfaceHeader
        variant="dark"
        title="Social"
        subtitle="Set goals, choose channels, set limits, and let HAM run your social presence."
      />

      {error ? (
        <WorkspaceSurfaceStateCard
          tone="amber"
          title="Social controls need attention"
          description={redactPlainText(error)}
        />
      ) : null}

      <Card title="Launch state">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-2xl font-semibold text-white">{statusLabel(profile)}</p>
              {!writesEnabled ? (
                <span className="rounded-full border border-amber-300/30 bg-amber-500/10 px-2 py-0.5 text-xs font-medium uppercase tracking-[0.08em] text-amber-100">
                  writes disabled
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-sm text-white/60">
              Goal: <span className="text-white/85">{goalDraft}</span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {profile.status === "draft" || profile.status === "stopped" ? (
              <Button
                type="button"
                onClick={() =>
                  void runAction("launch", () => socialAdapter.launchAutonomy(writeToken))
                }
                disabled={launchDisabled}
              >
                Launch
              </Button>
            ) : null}
            {profile.status === "running" ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() =>
                  void runAction("pause", () => socialAdapter.pauseAutonomy(writeToken))
                }
                disabled={writeControlsDisabled}
              >
                Pause
              </Button>
            ) : null}
            {profile.status === "paused" ? (
              <Button
                type="button"
                onClick={() =>
                  void runAction("resume", () => socialAdapter.launchAutonomy(writeToken))
                }
                disabled={writeControlsDisabled || profile.emergency_stop}
              >
                Resume
              </Button>
            ) : null}
            {profile.status === "running" || profile.status === "paused" ? (
              <Button
                type="button"
                variant="destructive"
                onClick={() =>
                  void runAction("stop", () => socialAdapter.stopAutonomy({}, writeToken))
                }
                disabled={writeControlsDisabled}
              >
                Stop
              </Button>
            ) : null}
            <Button
              type="button"
              variant="destructive"
              onClick={() =>
                void runAction("emergency-stop", () =>
                  socialAdapter.stopAutonomy({ emergency_stop: true }, writeToken),
                )
              }
              disabled={writeControlsDisabled || profile.emergency_stop}
            >
              Emergency stop
            </Button>
          </div>
        </div>
        {profileInvalid ? (
          <p className="mt-3 rounded-lg border border-amber-300/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            The backend returned a state HAM does not recognize, so launch is disabled until
            controls are refreshed.
          </p>
        ) : null}
        {profile.emergency_stop ? (
          <p className="mt-3 rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-100">
            Emergency stop is active. Launch stays disabled until the profile is reset by an
            operator.
          </p>
        ) : null}
        {loading ? <p className="mt-3 text-sm text-white/50">Loading current profile…</p> : null}
        <label className="mt-4 flex max-w-xl flex-col gap-2 text-sm text-white/70">
          <span>HAM_SOCIAL_AUTONOMY_WRITE_TOKEN (session only)</span>
          <input
            aria-label="HAM_SOCIAL_AUTONOMY_WRITE_TOKEN (session only)"
            autoComplete="off"
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white outline-none focus:border-emerald-300/50"
            type="password"
            value={writeToken}
            onChange={(event) => setWriteToken(event.target.value)}
          />
        </label>
        {writeTokenMissing ? (
          <p className="mt-2 text-xs text-white/50">
            Paste the session-only operator write token to enable launch controls.
          </p>
        ) : null}
      </Card>

      <SocialStatusPanel profile={profile} profileInvalid={profileInvalid} />

      <Card title="Goal">
        <label className="flex flex-col gap-2 text-sm text-white/70">
          <span>Current goal</span>
          <textarea
            className="min-h-20 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white outline-none focus:border-emerald-300/50"
            value={goalDraft}
            onChange={(event) => setGoalDraft(event.target.value)}
          />
        </label>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLE_GOALS.map((goal) => (
            <button
              key={goal}
              type="button"
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-white/75 hover:border-emerald-300/35"
              onClick={() => setGoalDraft(goal)}
            >
              {goal}
            </button>
          ))}
        </div>
      </Card>

      <Card title="Channels">
        <ul className="grid gap-2 md:grid-cols-3">
          {(["x", "telegram", "discord"] as const).map((channel) => (
            <li
              key={channel}
              className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-3"
            >
              <span className="font-medium text-white/90">
                {channel === "x" ? "X" : channel === "telegram" ? "Telegram" : "Discord"}
              </span>
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-xs text-white/70">
                {channelBadge(profile, channel)}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Limits">
        <form
          className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end"
          onSubmit={saveLimits}
        >
          <NumberField
            label="Posts per day"
            value={limits.postsPerDay}
            onChange={(value) => setLimits((current) => ({ ...current, postsPerDay: value }))}
          />
          <NumberField
            label="Replies per day"
            value={limits.repliesPerDay}
            onChange={(value) => setLimits((current) => ({ ...current, repliesPerDay: value }))}
          />
          <p className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white/75">
            Total daily actions: {totalDailyActions}
          </p>
          <Button type="submit" variant="secondary" disabled={writeControlsDisabled}>
            Save limits
          </Button>
        </form>
      </Card>

      <Card title="Safety boundaries">
        <ul className="grid gap-2 md:grid-cols-2">
          {SAFETY_BOUNDARIES.map((boundary) => (
            <li
              key={boundary}
              className="rounded-lg border border-emerald-300/15 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-50/85"
            >
              {boundary}
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="What HAM learned">
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-white/78">
            {learningText || "HAM is still gathering enough signal to share a useful lesson."}
          </p>
        </Card>
        <Card title="Recent activity">
          <p className="text-sm leading-relaxed text-white/78">
            {redactPlainText(formatActivity(profile))}
          </p>
        </Card>
      </div>
    </div>
  );
}
