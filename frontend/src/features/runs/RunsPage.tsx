import { useMemo } from "react";

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getChallenges, getRuns } from "@/api/endpoints";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatDateTime } from "@/features/runs/utils";

export function RunsPage() {
  const activeRunsQuery = useQuery({
    queryKey: ["runs", "active"],
    queryFn: () => getRuns({ activeOnly: true, limit: 200 }),
    refetchInterval: 2000,
  });

  const recentRunsQuery = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => getRuns({ limit: 30 }),
    refetchInterval: 5000,
  });

  const challengesQuery = useQuery({
    queryKey: ["challenges"],
    queryFn: getChallenges,
    staleTime: 30_000,
  });

  const challengeNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const challenge of challengesQuery.data?.items ?? []) {
      map.set(challenge.id, challenge.name);
    }
    return map;
  }, [challengesQuery.data]);

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold">Active Agent Runner Instances</h2>
            <p className="text-sm text-slate-600">Queued and running sandboxes refresh automatically.</p>
          </div>
          <Badge>{activeRunsQuery.data?.items.length ?? 0} active</Badge>
        </div>

        {activeRunsQuery.isLoading ? <p>Loading active runs...</p> : null}
        {activeRunsQuery.error ? <p className="text-danger">Failed to load active runs.</p> : null}
        {activeRunsQuery.data && activeRunsQuery.data.items.length === 0 ? <p className="text-sm text-slate-600">No active runs right now.</p> : null}

        {activeRunsQuery.data && activeRunsQuery.data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-2 py-2">Run</th>
                  <th className="px-2 py-2">Challenge</th>
                  <th className="px-2 py-2">Backend</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Started</th>
                </tr>
              </thead>
              <tbody>
                {activeRunsQuery.data.items.map((run) => (
                  <tr key={run.id} className="border-b border-slate-100 last:border-b-0">
                    <td className="px-2 py-3 font-semibold">
                      <Link className="text-accent hover:underline" to={`/runs/${run.id}`}>
                        {run.id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-2 py-3">
                      <Link className="text-accent hover:underline" to={`/challenges/${run.challenge_id}`}>
                        {challengeNames.get(run.challenge_id) ?? run.challenge_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-2 py-3">{run.backend}</td>
                    <td className="px-2 py-3">
                      <Badge status={run.status}>{run.status}</Badge>
                    </td>
                    <td className="px-2 py-3 text-slate-600">{formatDateTime(run.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <Card>
        <h3 className="mb-3 text-lg font-semibold">Recent Runs</h3>
        {recentRunsQuery.isLoading ? <p>Loading recent runs...</p> : null}
        {recentRunsQuery.error ? <p className="text-danger">Failed to load recent runs.</p> : null}
        {recentRunsQuery.data && recentRunsQuery.data.items.length === 0 ? <p className="text-sm text-slate-600">No runs yet.</p> : null}

        {recentRunsQuery.data && recentRunsQuery.data.items.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {recentRunsQuery.data.items.map((run) => (
              <li key={run.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2">
                <div className="flex items-center gap-2">
                  <Link className="font-semibold text-accent hover:underline" to={`/runs/${run.id}`}>
                    {run.id.slice(0, 8)}
                  </Link>
                  <span className="text-slate-600">{run.backend}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge status={run.status}>{run.status}</Badge>
                  <span className="text-xs text-slate-600">{formatDateTime(run.started_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </div>
  );
}
