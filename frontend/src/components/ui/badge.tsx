import type { HTMLAttributes } from "react";

import { cn } from "@/lib-utils";

const statusClasses: Record<string, string> = {
  queued: "border border-line bg-surface-strong text-ink-muted",
  running: "bg-accent-soft text-accent",
  flag_found: "bg-emerald-500/15 text-success",
  deliverable_produced: "bg-emerald-500/15 text-success",
  blocked: "bg-rose-500/15 text-danger",
  timeout: "bg-amber-500/15 text-warning",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status?: string;
}

export function Badge({ className, status, children, ...props }: BadgeProps) {
  const style = status ? statusClasses[status] ?? "border border-line bg-surface-muted text-ink-muted" : "border border-line bg-surface-muted text-ink-muted";
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide", style, className)}
      {...props}
    >
      {children}
    </span>
  );
}
