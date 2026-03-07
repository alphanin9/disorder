import { useEffect, useLayoutEffect, useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { continueRun, getChallenge, getRun, getRunLogs, getRunResult, terminateRun } from "@/api/endpoints";
import type { RunContinueRequest, RunContinuationType } from "@/api/models";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { inputCompactClasses } from "@/components/ui/forms";
import { formatDateTime, isRunFinal } from "@/features/runs/utils";

const MAX_LOG_BUFFER_BYTES = 8 * 1024 * 1024;
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const MAX_TEXT_PREVIEW = 2000;
const CONTINUATION_TYPE_OPTIONS: RunContinuationType[] = ["hint", "deliverable_fix", "strategy_change", "other"];

type JsonObject = Record<string, unknown>;

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function truncateText(value: string): string {
  if (value.length <= MAX_TEXT_PREVIEW) {
    return value;
  }
  return `${value.slice(0, MAX_TEXT_PREVIEW)}\n...[truncated ${value.length - MAX_TEXT_PREVIEW} chars]`;
}

function formatCommandExecution(item: JsonObject, eventType: string): string {
  const command = asString(item.command) || "<command>";
  const status = asString(item.status);
  const exitCode = item.exit_code;
  const output = asString(item.aggregated_output);

  if (eventType === "item.started") {
    return `$ ${command}`;
  }

  const statusText = status ? ` (${status})` : "";
  const exitText = typeof exitCode === "number" ? ` exit=${exitCode}` : "";
  const header = `$ ${command}${statusText}${exitText}`;
  if (!output) {
    return header;
  }
  return `${header}\n${truncateText(output)}`;
}

function formatCodexJsonLine(line: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return line;
  }

  if (!parsed || typeof parsed !== "object") {
    return line;
  }

  const payload = parsed as JsonObject;
  const eventType = asString(payload.type);
  if (!eventType) {
    return line;
  }

  if (eventType === "thread.started") {
    return `[thread] started ${asString(payload.thread_id)}`;
  }
  if (eventType === "turn.started") {
    return "[turn] started";
  }
  if (eventType === "turn.completed") {
    return "[turn] completed";
  }

  const itemValue = payload.item;
  if ((eventType === "item.started" || eventType === "item.completed") && itemValue && typeof itemValue === "object") {
    const item = itemValue as JsonObject;
    const itemType = asString(item.type);
    if (itemType === "command_execution") {
      return formatCommandExecution(item, eventType);
    }
    if (itemType === "reasoning") {
      return `[reasoning] ${asString(item.text)}`;
    }
    if (itemType === "agent_message") {
      return `[agent] ${asString(item.text)}`;
    }
    return `[${eventType}] ${itemType || "item"}`;
  }

  return line;
}

function renderParsedLogs(rawLogs: string): string {
  if (!rawLogs) {
    return "";
  }
  return rawLogs
    .split(/\r?\n/)
    .map((line) => formatCodexJsonLine(line))
    .join("\n");
}

export function RunPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { runId } = useParams();
  const [rawLogs, setRawLogs] = useState("");
  const [offset, setOffset] = useState(0);
  const [sseFailed, setSseFailed] = useState(false);
  const [logMode, setLogMode] = useState<"parsed" | "raw">("parsed");
  const [showContinuationForm, setShowContinuationForm] = useState(false);
  const [continuationMessage, setContinuationMessage] = useState("");
  const [continuationType, setContinuationType] = useState<RunContinuationType>("hint");
  const [timeLimitSeconds, setTimeLimitSeconds] = useState("");
  const [stopCriteriaOverride, setStopCriteriaOverride] = useState("");
  const [reuseParentArtifacts, setReuseParentArtifacts] = useState(true);
  const [continuationError, setContinuationError] = useState<string | null>(null);

  useLayoutEffect(() => {
    setRawLogs("");
    setOffset(0);
    setSseFailed(false);
  }, [runId]);

  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId ?? ""),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status && !isRunFinal(status) ? 1000 : false;
    },
  });

  const status = runQuery.data?.run.status;
  const terminal = Boolean(status && isRunFinal(status));
  const useSse = !sseFailed && typeof EventSource !== "undefined";
  const terminateMutation = useMutation({
    mutationFn: terminateRun,
    onSuccess: () => {
      if (!runId) {
        return;
      }
      void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["run-result", runId] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  const continuationMutation = useMutation({
    mutationFn: async (payload: RunContinueRequest) => continueRun(runId ?? "", payload),
    onSuccess: (childRun) => {
      setShowContinuationForm(false);
      setContinuationMessage("");
      setTimeLimitSeconds("");
      setStopCriteriaOverride("");
      setContinuationError(null);
      void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void navigate(`/runs/${childRun.id}`);
    },
  });

  useEffect(() => {
    if (!runId || !useSse) {
      return;
    }

    const source = new EventSource(`${API_BASE}/runs/${runId}/logs/stream`);
    source.onmessage = (event) => {
      try {
        const chunk = JSON.parse(event.data) as {
          logs: string;
          next_offset: number;
          eof: boolean;
        };

        if (chunk.logs) {
          setRawLogs((previous) => {
            const combined = previous + chunk.logs;
            if (combined.length <= MAX_LOG_BUFFER_BYTES) {
              return combined;
            }
            return combined.slice(combined.length - MAX_LOG_BUFFER_BYTES);
          });
        }
        setOffset(chunk.next_offset);

        if (chunk.eof) {
          source.close();
        }
      } catch {
        // Ignore malformed chunks and continue stream.
      }
    };
    source.onerror = () => {
      source.close();
      setSseFailed(true);
    };

    return () => {
      source.close();
    };
  }, [runId, useSse]);

  useEffect(() => {
    if (!runId || useSse) {
      return;
    }

    let timer: ReturnType<typeof setTimeout> | undefined;
    let active = true;

    const poll = async () => {
      try {
        const chunk = await getRunLogs(runId, offset);
        if (!active) {
          return;
        }

        if (chunk.logs) {
          setRawLogs((previous) => {
            const combined = previous + chunk.logs;
            if (combined.length <= MAX_LOG_BUFFER_BYTES) {
              return combined;
            }
            return combined.slice(combined.length - MAX_LOG_BUFFER_BYTES);
          });
        }

        if (chunk.next_offset !== offset) {
          setOffset(chunk.next_offset);
        }

        const shouldContinue = !chunk.eof || !terminal;
        if (shouldContinue) {
          timer = setTimeout(poll, 1000);
        }
      } catch {
        timer = setTimeout(poll, 1500);
      }
    };

    poll();

    return () => {
      active = false;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [offset, runId, terminal, useSse]);

  const resultQuery = useQuery({
    queryKey: ["run-result", runId],
    queryFn: () => getRunResult(runId ?? ""),
    enabled: Boolean(runId && terminal),
  });

  const runMeta = runQuery.data?.run;
  const challengeQuery = useQuery({
    queryKey: ["challenge", runMeta?.challenge_id],
    queryFn: () => getChallenge(runMeta?.challenge_id ?? ""),
    enabled: Boolean(runMeta?.challenge_id),
  });
  const parsedLogs = useMemo(() => renderParsedLogs(rawLogs), [rawLogs]);
  const logsToRender = logMode === "parsed" ? parsedLogs : rawLogs;
  const challengeName = challengeQuery.data?.name ?? resultQuery.data?.challenge_name;
  const ctfName = challengeQuery.data?.ctf_name;
  const challengeDisplay = [challengeName, ctfName].filter((value): value is string => Boolean(value)).join(" / ");
  const childRuns = runQuery.data?.child_runs ?? [];
  const parentRunId = runMeta?.parent_run_id;
  const details = useMemo(
    () => [
      ["Challenge / CTF", challengeDisplay || runMeta?.challenge_id || "-"],
      ["Backend", runMeta?.backend ?? "-"],
      ["Continuation depth", String(runMeta?.continuation_depth ?? 0)],
      ["Reasoning", String((runMeta?.budgets as Record<string, unknown> | undefined)?.reasoning_effort ?? "medium")],
      ["Budget (minutes)", String((runMeta?.budgets as Record<string, unknown> | undefined)?.max_minutes ?? 30)],
      ["Started", formatDateTime(runMeta?.started_at)],
      ["Finished", formatDateTime(runMeta?.finished_at)],
    ],
    [challengeDisplay, runMeta],
  );

  if (!runId) {
    return <p>Missing run id.</p>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <Link to="/" className="text-sm text-accent hover:underline">
              Back to challenges
            </Link>
            <h2 className="mt-2 text-xl font-bold">Run {runId}</h2>
          </div>
          <div className="flex items-center gap-2">
            {status && !isRunFinal(status) ? (
              <Button
                type="button"
                variant="ghost"
                className="h-8 px-3 text-xs text-warning hover:text-warning"
                disabled={terminateMutation.isPending}
                onClick={() => {
                  if (!window.confirm(`Force terminate run ${runId.slice(0, 8)}?`)) {
                    return;
                  }
                  terminateMutation.mutate(runId);
                }}
              >
                Force stop
              </Button>
            ) : null}
            {terminal ? (
              <Button
                type="button"
                variant="secondary"
                className="h-8 px-3 text-xs"
                onClick={() => {
                  setShowContinuationForm((current) => !current);
                }}
              >
                Continue run
              </Button>
            ) : null}
            <Badge status={status}>{status ?? "loading"}</Badge>
          </div>
        </div>

        {runQuery.isLoading ? <p>Loading run state...</p> : null}
        {runQuery.error ? <p className="text-danger">Failed to load run state.</p> : null}
        {terminateMutation.isError ? <p className="mb-2 text-sm text-danger">Failed to terminate run.</p> : null}

        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          {details.map(([label, value]) => (
            <div key={label} className="rounded-md bg-surface-muted px-3 py-2">
              <dt className="text-xs uppercase tracking-wide text-ink-subtle">{label}</dt>
              <dd className="font-medium text-ink">{value}</dd>
            </div>
          ))}
        </dl>

        {parentRunId || childRuns.length > 0 ? (
          <div className="mt-4 space-y-2 rounded-md border border-line bg-surface-muted p-3 text-sm">
            <p className="text-xs uppercase tracking-wide text-ink-subtle">Lineage</p>
            {parentRunId ? (
              <p>
                Parent run:{" "}
                <Link className="font-semibold text-accent hover:underline" to={`/runs/${parentRunId}`}>
                  {parentRunId.slice(0, 8)}
                </Link>
              </p>
            ) : (
              <p>Parent run: none</p>
            )}
            <div>
              Child runs:{" "}
              {childRuns.length === 0
                ? "none"
                : childRuns.map((childRun) => (
                    <Link key={childRun.id} className="mr-2 font-semibold text-accent hover:underline" to={`/runs/${childRun.id}`}>
                      {childRun.id.slice(0, 8)}
                    </Link>
                  ))}
            </div>
          </div>
        ) : null}

        {showContinuationForm ? (
          <div className="mt-4 space-y-3 rounded-md border border-line bg-surface-muted p-3">
            <h3 className="text-sm font-semibold">Continue this run</h3>
            <label className="block space-y-1 text-xs text-ink-muted">
              <span>Message</span>
              <textarea
                className={`${inputCompactClasses} min-h-24`}
                rows={4}
                value={continuationMessage}
                onChange={(event) => {
                  setContinuationMessage(event.target.value);
                }}
                placeholder="Describe what to fix or try next..."
              />
            </label>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block space-y-1 text-xs text-ink-muted">
                <span>Type</span>
                <select
                  className={inputCompactClasses}
                  value={continuationType}
                  onChange={(event) => {
                    setContinuationType(event.target.value as RunContinuationType);
                  }}
                >
                  {CONTINUATION_TYPE_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1 text-xs text-ink-muted">
                <span>Time limit override (seconds)</span>
                <input
                  type="number"
                  min={60}
                  className={inputCompactClasses}
                  value={timeLimitSeconds}
                  onChange={(event) => {
                    setTimeLimitSeconds(event.target.value);
                  }}
                  placeholder="optional"
                />
              </label>
            </div>
            <label className="block space-y-1 text-xs text-ink-muted">
              <span>Stop criteria override (JSON object, optional)</span>
              <textarea
                className={`${inputCompactClasses} font-mono text-xs`}
                rows={4}
                value={stopCriteriaOverride}
                onChange={(event) => {
                  setStopCriteriaOverride(event.target.value);
                }}
                placeholder='{"secondary":{"config":{"required_files":["README.md","solve.py"]}}}'
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-ink-muted">
              <input
                type="checkbox"
                checked={reuseParentArtifacts}
                onChange={(event) => {
                  setReuseParentArtifacts(event.target.checked);
                }}
              />
              Reuse parent artifacts/context
            </label>
            {continuationError ? <p className="text-xs text-danger">{continuationError}</p> : null}
            {continuationMutation.isError ? <p className="text-xs text-danger">Failed to create continuation run.</p> : null}
            <div className="flex items-center gap-2">
              <Button
                type="button"
                className="h-8 px-3 text-xs"
                disabled={continuationMutation.isPending}
                onClick={() => {
                  const message = continuationMessage.trim();
                  if (!message) {
                    setContinuationError("Message is required.");
                    return;
                  }
                  let parsedStopCriteria: Record<string, unknown> | undefined;
                  const rawStop = stopCriteriaOverride.trim();
                  if (rawStop) {
                    try {
                      const parsed = JSON.parse(rawStop);
                      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                        setContinuationError("Stop criteria override must be a JSON object.");
                        return;
                      }
                      parsedStopCriteria = parsed as Record<string, unknown>;
                    } catch {
                      setContinuationError("Stop criteria override is not valid JSON.");
                      return;
                    }
                  }

                  const payload: RunContinueRequest = {
                    message,
                    type: continuationType,
                    reuse_parent_artifacts: reuseParentArtifacts,
                  };
                  if (timeLimitSeconds.trim()) {
                    const parsed = Number.parseInt(timeLimitSeconds, 10);
                    if (Number.isNaN(parsed) || parsed < 60) {
                      setContinuationError("Time limit override must be at least 60 seconds.");
                      return;
                    }
                    payload.time_limit_seconds = parsed;
                  }
                  if (parsedStopCriteria) {
                    payload.stop_criteria_override = parsedStopCriteria;
                  }

                  setContinuationError(null);
                  continuationMutation.mutate(payload);
                }}
              >
                Start continuation
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="h-8 px-3 text-xs"
                onClick={() => {
                  setShowContinuationForm(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </Card>

      <Card>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Live Logs</h3>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant={logMode === "parsed" ? "secondary" : "ghost"}
              className="h-7 px-2 text-xs"
              onClick={() => {
                setLogMode("parsed");
              }}
            >
              Parsed
            </Button>
            <Button
              type="button"
              variant={logMode === "raw" ? "secondary" : "ghost"}
              className="h-7 px-2 text-xs"
              onClick={() => {
                setLogMode("raw");
              }}
            >
              Raw JSONL
            </Button>
          </div>
        </div>
        <pre className="max-h-96 overflow-auto rounded-md border border-line bg-slate-950 p-3 text-xs text-emerald-300 shadow-inner">
          {logsToRender || "(no logs yet)"}
        </pre>
      </Card>

      <Card>
        <h3 className="mb-2 text-lg font-semibold">Final Result</h3>
        {!terminal ? <p className="text-sm text-ink-muted">Result will appear when run reaches a terminal state.</p> : null}
        {resultQuery.isLoading ? <p>Loading result...</p> : null}
        {resultQuery.error ? <p className="text-danger">Failed to load result payload.</p> : null}
        {resultQuery.data ? (
          <div className="space-y-3 text-sm">
            <div className="rounded-md bg-surface-muted px-3 py-2">
              <p>
                <span className="font-semibold">Status:</span> {resultQuery.data.status}
              </p>
              <p>
                <span className="font-semibold">Stop criterion:</span> {resultQuery.data.stop_criterion_met}
              </p>
            </div>
            <pre className="max-h-[28rem] overflow-auto rounded-md bg-surface-strong p-3 text-xs text-ink">
              {JSON.stringify(resultQuery.data, null, 2)}
            </pre>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
