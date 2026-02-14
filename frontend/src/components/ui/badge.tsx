import type { HTMLAttributes } from "react";

import { cn } from "@/lib-utils";

const statusClasses: Record<string, string> = {
  queued: "bg-slate-200 text-slate-800",
  running: "bg-accentSoft text-accent",
  flag_found: "bg-emerald-100 text-success",
  deliverable_produced: "bg-emerald-100 text-success",
  blocked: "bg-rose-100 text-danger",
  timeout: "bg-amber-100 text-warning",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status?: string;
}

export function Badge({ className, status, children, ...props }: BadgeProps) {
  const style = status ? statusClasses[status] ?? "bg-slate-200 text-slate-700" : "bg-slate-100 text-slate-700";
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide", style, className)}
      {...props}
    >
      {children}
    </span>
  );
}
