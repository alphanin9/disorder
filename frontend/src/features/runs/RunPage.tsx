import { useEffect, useMemo, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getRun, getRunLogs, getRunResult } from "@/api/endpoints";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatDateTime, isRunFinal } from "@/features/runs/utils";

const MAX_LOG_BUFFER_BYTES = 8 * 1024 * 1024;

export function RunPage() {
  const { runId } = useParams();
  const [logs, setLogs] = useState("");
  const [offset, setOffset] = useState(0);

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

  useEffect(() => {
    if (!runId) {
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
          setLogs((previous) => {
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
  }, [offset, runId, terminal]);

  const resultQuery = useQuery({
    queryKey: ["run-result", runId],
    queryFn: () => getRunResult(runId ?? ""),
    enabled: Boolean(runId && terminal),
  });

  const runMeta = runQuery.data?.run;
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
          <Badge status={status}>{status ?? "loading"}</Badge>
        </div>

        {runQuery.isLoading ? <p>Loading run state...</p> : null}
        {runQuery.error ? <p className="text-danger">Failed to load run state.</p> : null}

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
        <h3 className="mb-2 text-lg font-semibold">Live Logs</h3>
        <pre className="max-h-96 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-emerald-300">{logs || "(no logs yet)"}</pre>
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
