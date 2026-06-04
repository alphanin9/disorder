import type { ClaudeAuthFile } from "@/api/models";
import { cn } from "@/lib-utils";

type ClaudeUsageWindow = {
  utilization?: number | null;
  resets_at?: string | null;
};

type ExtraUsage = {
  currency?: string | null;
  is_enabled?: boolean | null;
  utilization?: number | null;
  used_credits?: number | null;
  monthly_limit?: number | null;
  disabled_reason?: string | null;
};

type ClaudeUsageSnapshot = {
  five_hour?: ClaudeUsageWindow | null;
  seven_day?: ClaudeUsageWindow | null;
  seven_day_sonnet?: ClaudeUsageWindow | null;
  seven_day_opus?: ClaudeUsageWindow | null;
  seven_day_oauth_apps?: ClaudeUsageWindow | null;
  seven_day_cowork?: ClaudeUsageWindow | null;
  extra_usage?: ExtraUsage | null;
};

type UsageWindowItem = {
  key: keyof ClaudeUsageSnapshot;
  label: string;
  window: ClaudeUsageWindow;
};

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function asUsageWindow(value: unknown): ClaudeUsageWindow | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  return {
    utilization: asNumber(record.utilization),
    resets_at: typeof record.resets_at === "string" ? record.resets_at : null,
  };
}

function asExtraUsage(value: unknown): ExtraUsage | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  return {
    currency: typeof record.currency === "string" ? record.currency : null,
    is_enabled: asBoolean(record.is_enabled),
    utilization: asNumber(record.utilization),
    used_credits: asNumber(record.used_credits),
    monthly_limit: asNumber(record.monthly_limit),
    disabled_reason: typeof record.disabled_reason === "string" ? record.disabled_reason : null,
  };
}

function parseSnapshot(snapshot: ClaudeAuthFile["usage_snapshot"]): ClaudeUsageSnapshot | null {
  if (!snapshot || typeof snapshot !== "object") {
    return null;
  }
  return {
    five_hour: asUsageWindow(snapshot.five_hour),
    seven_day: asUsageWindow(snapshot.seven_day),
    seven_day_sonnet: asUsageWindow(snapshot.seven_day_sonnet),
    seven_day_opus: asUsageWindow(snapshot.seven_day_opus),
    seven_day_oauth_apps: asUsageWindow(snapshot.seven_day_oauth_apps),
    seven_day_cowork: asUsageWindow(snapshot.seven_day_cowork),
    extra_usage: asExtraUsage(snapshot.extra_usage),
  };
}

function formatReset(resetsAt: string | null | undefined): string | null {
  if (!resetsAt) {
    return null;
  }
  const timestamp = new Date(resetsAt).getTime();
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  const deltaMs = timestamp - Date.now();
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

function UsageBar({ item }: { item: UsageWindowItem }) {
  const used = item.window.utilization;
  if (used === null || used === undefined) {
    return null;
  }
  const clamped = Math.max(0, Math.min(100, Math.round(used)));
  const reset = formatReset(item.window.resets_at);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium text-ink">{item.label}</span>
        <span className="text-ink-muted">
          {clamped}% used{reset ? <span className="ml-1 text-ink-subtle">- {reset}</span> : null}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-strong">
        <div className={cn("h-full rounded-full transition-all", barColor(clamped))} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

function ExtraUsageLine({ extraUsage }: { extraUsage: ExtraUsage }) {
  const utilization =
    extraUsage.utilization == null ? null : Math.max(0, Math.min(100, Math.round(extraUsage.utilization)));
  const currency = extraUsage.currency ? extraUsage.currency.toUpperCase() : null;
  const creditText =
    extraUsage.used_credits != null && extraUsage.monthly_limit != null
      ? `${extraUsage.used_credits} / ${extraUsage.monthly_limit}${currency ? ` ${currency}` : ""}`
      : null;

  return (
    <div className="rounded bg-surface-strong px-2 py-1.5 text-xs text-ink-muted">
      <span className="font-medium text-ink">Extra usage</span>
      {utilization !== null ? <span className="ml-2">{utilization}% used</span> : null}
      {creditText ? <span className="ml-2">{creditText}</span> : null}
    </div>
  );
}

export function ClaudeUsage({ file }: { file: ClaudeAuthFile }) {
  const snapshot = parseSnapshot(file.usage_snapshot);
  if (!snapshot) {
    return null;
  }

  const allWindows: UsageWindowItem[] = [
    { key: "five_hour", label: "5h window", window: snapshot.five_hour ?? {} },
    { key: "seven_day", label: "7d window", window: snapshot.seven_day ?? {} },
    { key: "seven_day_sonnet", label: "7d Sonnet", window: snapshot.seven_day_sonnet ?? {} },
    { key: "seven_day_opus", label: "7d Opus", window: snapshot.seven_day_opus ?? {} },
    { key: "seven_day_oauth_apps", label: "7d OAuth apps", window: snapshot.seven_day_oauth_apps ?? {} },
    { key: "seven_day_cowork", label: "7d Cowork", window: snapshot.seven_day_cowork ?? {} },
  ];
  const windows = allWindows.filter((item) => item.window.utilization != null);

  const showExtraUsage = Boolean(
    snapshot.extra_usage &&
      (snapshot.extra_usage.is_enabled ||
        snapshot.extra_usage.utilization != null ||
        snapshot.extra_usage.used_credits != null),
  );

  if (windows.length === 0 && !showExtraUsage) {
    return null;
  }

  return (
    <div className="mt-2 space-y-2 rounded-md border border-line bg-surface px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Current usage</span>
      </div>
      <div className="space-y-2">
        {windows.map((item) => (
          <UsageBar key={item.key} item={item} />
        ))}
        {showExtraUsage && snapshot.extra_usage ? <ExtraUsageLine extraUsage={snapshot.extra_usage} /> : null}
      </div>
    </div>
  );
}
