export const FINAL_RUN_STATUSES = new Set(["flag_found", "deliverable_produced", "blocked", "timeout"]);

export function isRunFinal(status: string): boolean {
  return FINAL_RUN_STATUSES.has(status);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
