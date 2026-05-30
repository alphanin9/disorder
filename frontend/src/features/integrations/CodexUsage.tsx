import type { CodexAuthFile } from "@/api/models";
import { cn } from "@/lib-utils";

type QuotaWindow = {
  used_percent?: number | null;
  window_minutes?: number | null;
  reset_at_ms?: number | null;
};

type QuotaSnapshot = {
  status?: number | null;
  plan_type?: string | null;
  active_limit?: number | null;
  primary?: QuotaWindow | null;
  secondary?: QuotaWindow | null;
};

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asWindow(value: unknown): QuotaWindow | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  return {
    used_percent: asNumber(record.used_percent),
    window_minutes: asNumber(record.window_minutes),
    reset_at_ms: asNumber(record.reset_at_ms),
  };
}

function parseSnapshot(snapshot: CodexAuthFile["quota_snapshot"]): QuotaSnapshot | null {
  if (!snapshot || typeof snapshot !== "object") {
    return null;
  }
  return {
    status: asNumber(snapshot.status),
    plan_type: typeof snapshot.plan_type === "string" ? snapshot.plan_type : null,
    active_limit: asNumber(snapshot.active_limit),
    primary: asWindow(snapshot.primary),
    secondary: asWindow(snapshot.secondary),
  };
}

function windowLabel(windowMinutes: number | null): string {
  if (windowMinutes === null || windowMinutes <= 0) {
    return "Quota";
  }
  if (windowMinutes % 1440 === 0) {
    return `${windowMinutes / 1440}d window`;
  }
  if (windowMinutes % 60 === 0) {
    return `${windowMinutes / 60}h window`;
  }
  return `${windowMinutes}m window`;
}

function formatReset(resetAtMs: number | null): string | null {
  if (resetAtMs === null || resetAtMs <= 0) {
    return null;
  }
  const deltaMs = resetAtMs - Date.now();
  if (deltaMs <= 0) {
    return "resets now";
  }
  const minutes = Math.round(deltaMs / 60000);
  if (minutes < 60) {
    return `resets in ${minutes}m`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    return `resets in ${hours}h`;
  }
  return `resets in ${Math.round(hours / 24)}d`;
}

function barColor(usedPercent: number): string {
  if (usedPercent >= 100) {
    return "bg-danger";
  }
  if (usedPercent >= 80) {
    return "bg-warning";
  }
  return "bg-success";
}

function UsageBar({ window }: { window: QuotaWindow }) {
  const used = window.used_percent;
  if (used === null || used === undefined) {
    return null;
  }
  const clamped = Math.max(0, Math.min(100, Math.round(used)));
  const reset = formatReset(window.reset_at_ms ?? null);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium text-ink">{windowLabel(window.window_minutes ?? null)}</span>
        <span className="text-ink-muted">
          {clamped}% used{reset ? <span className="ml-1 text-ink-subtle">· {reset}</span> : null}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-strong">
        <div className={cn("h-full rounded-full transition-all", barColor(clamped))} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

export function CodexUsage({ file }: { file: CodexAuthFile }) {
  const snapshot = parseSnapshot(file.quota_snapshot);
  const windows = snapshot ? [snapshot.primary, snapshot.secondary].filter((w): w is QuotaWindow => Boolean(w && w.used_percent !== null && w.used_percent !== undefined)) : [];

  if (windows.length === 0) {
    return null;
  }

  const rateLimited = snapshot?.status === 429;

  return (
    <div className="mt-2 space-y-2 rounded-md border border-line bg-surface px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Current usage</span>
        <div className="flex items-center gap-1.5">
          {snapshot?.plan_type ? (
            <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">{snapshot.plan_type}</span>
          ) : null}
          {rateLimited ? (
            <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-[11px] font-semibold text-danger">rate-limited</span>
          ) : null}
        </div>
      </div>
      <div className="space-y-2">
        {windows.map((window, index) => (
          <UsageBar key={window.window_minutes ?? index} window={window} />
        ))}
      </div>
    </div>
  );
}
