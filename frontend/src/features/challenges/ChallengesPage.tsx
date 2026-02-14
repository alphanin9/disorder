import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getChallenges } from "@/api/endpoints";
import { Card } from "@/components/ui/card";

export function ChallengesPage() {
  const query = useQuery({
    queryKey: ["challenges"],
    queryFn: getChallenges,
  });

  return (
    <Card>
      <h2 className="mb-1 text-lg font-bold">Challenges</h2>
      <p className="mb-5 text-sm text-slate-600">Select a challenge to inspect details and start a run.</p>

      {query.isLoading ? <p>Loading challenges...</p> : null}
      {query.error ? <p className="text-danger">Failed to load challenges.</p> : null}

      {query.data ? (
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-2 py-2">Name</th>
                <th className="px-2 py-2">Category</th>
                <th className="px-2 py-2">Points</th>
                <th className="px-2 py-2">Synced</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((challenge) => (
                <tr key={challenge.id} className="border-b border-slate-100 last:border-b-0">
                  <td className="px-2 py-3 font-semibold">
                    <Link className="text-accent hover:underline" to={`/challenges/${challenge.id}`}>
                      {challenge.name}
                    </Link>
                  </td>
                  <td className="px-2 py-3">{challenge.category}</td>
                  <td className="px-2 py-3">{challenge.points}</td>
                  <td className="px-2 py-3 text-slate-600">{new Date(challenge.synced_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}
