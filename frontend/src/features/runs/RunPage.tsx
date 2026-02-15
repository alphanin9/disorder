import { useEffect, useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getRun, getRunLogs, getRunResult, terminateRun } from "@/api/endpoints";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatDateTime, isRunFinal } from "@/features/runs/utils";

const MAX_LOG_BUFFER_BYTES = 8 * 1024 * 1024;
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const MAX_TEXT_PREVIEW = 2000;

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
  const queryClient = useQueryClient();
  const { runId } = useParams();
  const [rawLogs, setRawLogs] = useState("");
  const [offset, setOffset] = useState(0);
  const [sseFailed, setSseFailed] = useState(false);
  const [logMode, setLogMode] = useState<"parsed" | "raw">("parsed");

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
  const parsedLogs = useMemo(() => renderParsedLogs(rawLogs), [rawLogs]);
  const logsToRender = logMode === "parsed" ? parsedLogs : rawLogs;
  const details = useMemo(
    () => [
      ["Run ID", runMeta?.id ?? "-"],
      ["Backend", runMeta?.backend ?? "-"],
      ["Started", formatDateTime(runMeta?.started_at)],
      ["Finished", formatDateTime(runMeta?.finished_at)],
    ],
    [runMeta],
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
            <Badge status={status}>{status ?? "loading"}</Badge>
          </div>
        </div>

        {runQuery.isLoading ? <p>Loading run state...</p> : null}
        {runQuery.error ? <p className="text-danger">Failed to load run state.</p> : null}
        {terminateMutation.isError ? <p className="mb-2 text-sm text-danger">Failed to terminate run.</p> : null}

        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          {details.map(([label, value]) => (
            <div key={label} className="rounded-md bg-slate-50 px-3 py-2">
              <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
              <dd className="font-medium text-slate-900">{value}</dd>
            </div>
          ))}
        </dl>
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
        <pre className="max-h-96 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-emerald-300">{logsToRender || "(no logs yet)"}</pre>
      </Card>

      <Card>
        <h3 className="mb-2 text-lg font-semibold">Final Result</h3>
        {!terminal ? <p className="text-sm text-slate-600">Result will appear when run reaches a terminal state.</p> : null}
        {resultQuery.isLoading ? <p>Loading result...</p> : null}
        {resultQuery.error ? <p className="text-danger">Failed to load result payload.</p> : null}
        {resultQuery.data ? (
          <div className="space-y-3 text-sm">
            <div className="rounded-md bg-slate-50 px-3 py-2">
              <p>
                <span className="font-semibold">Status:</span> {resultQuery.data.status}
              </p>
              <p>
                <span className="font-semibold">Stop criterion:</span> {resultQuery.data.stop_criterion_met}
              </p>
            </div>
            <pre className="max-h-[28rem] overflow-auto rounded-md bg-slate-100 p-3 text-xs text-slate-800">
              {JSON.stringify(resultQuery.data, null, 2)}
            </pre>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
