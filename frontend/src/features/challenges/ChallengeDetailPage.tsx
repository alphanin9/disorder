import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { createRun, getChallenge } from "@/api/endpoints";
import type { RunCreateRequest } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const runSchema = z.object({
  backend: z.enum(["mock", "codex", "claude_code"]),
  local_deploy_enabled: z.boolean().default(false),
});

type RunForm = z.infer<typeof runSchema>;

export function ChallengeDetailPage() {
  const { challengeId } = useParams();
  const navigate = useNavigate();

  const challengeQuery = useQuery({
    queryKey: ["challenge", challengeId],
    queryFn: () => getChallenge(challengeId ?? ""),
    enabled: Boolean(challengeId),
  });

  const form = useForm<RunForm>({
    resolver: zodResolver(runSchema),
    defaultValues: {
      backend: "mock",
      local_deploy_enabled: false,
    },
  });

  const runMutation = useMutation({
    mutationFn: (values: RunForm) => {
      const payload: RunCreateRequest = {
        challenge_id: challengeId ?? "",
        backend: values.backend,
        local_deploy_enabled: values.local_deploy_enabled,
      };
      return createRun(payload);
    },
    onSuccess: (run) => {
      navigate(`/runs/${run.id}`);
    },
  });

  if (!challengeId) {
    return <p>Missing challenge id.</p>;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card>
        <div className="mb-2">
          <Link to="/" className="text-sm text-accent hover:underline">
            Back to challenges
          </Link>
        </div>
        {challengeQuery.isLoading ? <p>Loading challenge...</p> : null}
        {challengeQuery.error ? <p className="text-danger">Failed to load challenge.</p> : null}
        {challengeQuery.data ? (
          <>
            <h2 className="text-xl font-bold">{challengeQuery.data.name}</h2>
            <p className="mt-1 text-sm text-slate-600">
              {challengeQuery.data.category} - {challengeQuery.data.points} pts
            </p>

            <section className="mt-6">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Description</h3>
              <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-800">
                {challengeQuery.data.description_md}
              </pre>
            </section>

            <section className="mt-6">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Artifacts</h3>
              {challengeQuery.data.artifacts.length === 0 ? <p className="text-sm text-slate-600">No artifacts synced.</p> : null}
              <ul className="space-y-2 text-sm">
                {challengeQuery.data.artifacts.map((artifact, index) => (
                  <li key={`${String(artifact.name)}-${index}`} className="rounded-md bg-slate-50 px-3 py-2">
                    {String(artifact.name)}
                  </li>
                ))}
              </ul>
            </section>
          </>
        ) : null}
      </Card>

      <Card>
        <h3 className="mb-3 text-lg font-semibold">Start Run</h3>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => {
            runMutation.mutate(values);
          })}
        >
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="backend">
              Backend
            </label>
            <select id="backend" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("backend")}>
              <option value="mock">mock</option>
              <option value="codex">codex</option>
              <option value="claude_code">claude_code</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("local_deploy_enabled")} />
            Enable local deploy (if compose file present)
          </label>

          {runMutation.isError ? <p className="text-sm text-danger">Failed to start run.</p> : null}

          <Button type="submit" className="w-full" disabled={runMutation.isPending}>
            {runMutation.isPending ? "Starting..." : "Start Run"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
