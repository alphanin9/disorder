import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { createChallenge, deleteChallenge, getChallenges, getCtfs, getRuns, uploadChallengeArtifact } from "@/api/endpoints";
import type { ChallengeArtifact, ChallengeCreateRequest, ChallengeManifest, CTF } from "@/api/models";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ArtifactDropzone } from "@/features/challenges/ArtifactDropzone";
import { CTFdImportCard } from "@/features/integrations/CTFdImportCard";

const createChallengeSchema = z.object({
  name: z.string().min(1, "Name is required"),
  category: z.string().min(1, "Category is required"),
  points: z.coerce.number().int().min(0),
  description_md: z.string().min(1, "Description is required"),
  flag_regex: z.string().optional(),
});

type CreateChallengeValues = z.infer<typeof createChallengeSchema>;

type ChallengeRunStats = {
  total: number;
  active: number;
  flagFound: number;
  deliverablesProduced: number;
  blockedOrTimeout: number;
};

const EMPTY_RUN_STATS: ChallengeRunStats = {
  total: 0,
  active: 0,
  flagFound: 0,
  deliverablesProduced: 0,
  blockedOrTimeout: 0,
};

function normalizeOptional(value: string | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : null;
}

function formatSyncedAt(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return value;
  }
  return parsed.toLocaleString();
}

export function ChallengesPage() {
  const queryClient = useQueryClient();
  const [artifacts, setArtifacts] = useState<ChallengeArtifact[]>([]);
  const [selectedCtfId, setSelectedCtfId] = useState<string | null>(null);

  const ctfQuery = useQuery({
    queryKey: ["ctfs"],
    queryFn: getCtfs,
  });

  const challengeQuery = useQuery({
    queryKey: ["challenges", selectedCtfId],
    queryFn: () => getChallenges({ ctfId: selectedCtfId ?? undefined }),
    enabled: Boolean(selectedCtfId),
  });

  const form = useForm<CreateChallengeValues>({
    resolver: zodResolver(createChallengeSchema),
    defaultValues: {
      name: "",
      category: "misc",
      points: 0,
      description_md: "",
      flag_regex: "",
    },
  });

  useEffect(() => {
    form.reset({
      name: "",
      category: "misc",
      points: 0,
      description_md: "",
      flag_regex: "",
    });
    setArtifacts([]);
  }, [form, selectedCtfId]);

  const createMutation = useMutation({
    mutationFn: (values: CreateChallengeValues) => {
      if (!selectedCtfId) {
        throw new Error("CTF is required");
      }

      const payload: ChallengeCreateRequest = {
        ctf_id: selectedCtfId,
        name: values.name.trim(),
        category: values.category.trim(),
        points: values.points,
        description_md: values.description_md.trim(),
        description_raw: values.description_md.trim(),
        platform: "manual",
        artifacts,
        remote_endpoints: [],
        local_deploy_hints: {
          compose_present: artifacts.some((artifact) => ["docker-compose.yml", "compose.yml"].includes(artifact.name)),
          notes: null,
        },
        flag_regex: normalizeOptional(values.flag_regex),
      };
      return createChallenge(payload);
    },
    onSuccess: () => {
      form.reset({
        name: "",
        category: "misc",
        points: 0,
        description_md: "",
        flag_regex: "",
      });
      setArtifacts([]);
      void queryClient.invalidateQueries({ queryKey: ["challenges"] });
    },
  });

  const uploadArtifactMutation = useMutation({
    mutationFn: uploadChallengeArtifact,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteChallenge,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["challenges"] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const onArtifactFilesSelected = async (files: File[]) => {
    for (const file of files) {
      try {
        const uploaded = await uploadArtifactMutation.mutateAsync(file);
        setArtifacts((previous) => {
          if (previous.some((artifact) => artifact.object_key === uploaded.object_key)) {
            return previous;
          }
          return [...previous, uploaded];
        });
      } catch {
        return;
      }
    }
  };

  const selectedCtf = useMemo<CTF | null>(() => {
    if (!selectedCtfId) {
      return null;
    }
    return ctfQuery.data?.items.find((ctf) => ctf.id === selectedCtfId) ?? null;
  }, [ctfQuery.data, selectedCtfId]);

  const challenges = useMemo<ChallengeManifest[]>(() => {
    return [...(challengeQuery.data?.items ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  }, [challengeQuery.data]);

  const challengeIds = useMemo(() => challenges.map((challenge) => challenge.id), [challenges]);

  const runsQuery = useQuery({
    queryKey: ["runs", "challenge-indicators", selectedCtfId, challengeIds],
    queryFn: async () => {
      const runsByChallenge = await Promise.all(
        challengeIds.map(async (challengeId) => {
          const response = await getRuns({ challengeId, limit: 500 });
          return response.items;
        }),
      );
      return runsByChallenge.flat();
    },
    enabled: Boolean(selectedCtfId) && challengeIds.length > 0,
    refetchInterval: 5000,
  });

  const runStatsByChallenge = useMemo(() => {
    const challengeIdSet = new Set(challenges.map((challenge) => challenge.id));
    const statsMap = new Map<string, ChallengeRunStats>();

    for (const run of runsQuery.data ?? []) {
      if (!challengeIdSet.has(run.challenge_id)) {
        continue;
      }

      const stats = statsMap.get(run.challenge_id) ?? { ...EMPTY_RUN_STATS };
      stats.total += 1;

      if (run.status === "queued" || run.status === "running") {
        stats.active += 1;
      }
      if (run.status === "flag_found") {
        stats.flagFound += 1;
      }
      if (run.status === "deliverable_produced") {
        stats.deliverablesProduced += 1;
      }
      if (run.status === "blocked" || run.status === "timeout") {
        stats.blockedOrTimeout += 1;
      }

      statsMap.set(run.challenge_id, stats);
    }

    return statsMap;
  }, [challenges, runsQuery.data]);

  if (!selectedCtfId) {
    return (
      <Card>
        <h2 className="mb-1 text-lg font-bold">CTF Events</h2>
        <p className="mb-5 text-sm text-slate-600">Select a CTF to open its challenges.</p>

        {ctfQuery.isLoading ? <p>Loading CTFs...</p> : null}
        {ctfQuery.error ? <p className="text-danger">Failed to load CTFs.</p> : null}

        {ctfQuery.data?.items.length === 0 ? (
          <p className="text-sm text-slate-600">
            No CTF events yet. Create one on the <Link to="/ctfs" className="font-semibold underline">CTFs page</Link>.
          </p>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {(ctfQuery.data?.items ?? []).map((ctf) => (
            <button
              key={ctf.id}
              type="button"
              className="rounded-lg border border-slate-200 p-4 text-left transition hover:border-accent/50 hover:bg-slate-50"
              onClick={() => {
                setSelectedCtfId(ctf.id);
              }}
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <h3 className="text-base font-bold text-ink">{ctf.name}</h3>
                <Badge>{ctf.platform ?? "manual"}</Badge>
              </div>
              <p className="text-xs text-slate-600">slug: {ctf.slug}</p>
              <p className="mt-2 text-xs text-slate-700">
                default flag regex: <code>{ctf.default_flag_regex ?? "(none)"}</code>
              </p>
              <p className="mt-3 text-sm font-semibold text-accent">Open challenges</p>
            </button>
          ))}
        </div>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card>
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <Button
              variant="ghost"
              type="button"
              className="mb-2 px-0 py-0 text-sm text-accent hover:bg-transparent hover:underline"
              onClick={() => {
                setSelectedCtfId(null);
              }}
            >
              Back to CTFs
            </Button>
            <h2 className="text-lg font-bold">{selectedCtf?.name ?? "Selected CTF"}</h2>
            <p className="text-sm text-slate-600">Challenges for this CTF.</p>
          </div>
          {selectedCtf ? <Badge>{selectedCtf.platform ?? "manual"}</Badge> : null}
        </div>

        <p className="mb-4 text-xs text-slate-600">
          Default flag regex: <code>{selectedCtf?.default_flag_regex ?? "(none)"}</code>
        </p>

        {challengeQuery.isLoading ? <p>Loading challenges...</p> : null}
        {challengeQuery.error ? <p className="text-danger">Failed to load challenges.</p> : null}
        {runsQuery.isLoading ? <p className="text-xs text-slate-600">Loading run indicators...</p> : null}
        {runsQuery.error ? <p className="text-xs text-danger">Run indicators unavailable.</p> : null}
        {challenges.length === 0 ? <p className="text-sm text-slate-600">No challenges yet for this CTF.</p> : null}

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {challenges.map((challenge) => {
            const runStats = runStatsByChallenge.get(challenge.id) ?? EMPTY_RUN_STATS;
            return (
              <div key={challenge.id} className="rounded-lg border border-slate-200 p-3">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <Link className="font-semibold text-accent hover:underline" to={`/challenges/${challenge.id}`}>
                    {challenge.name}
                  </Link>
                  <Badge>{challenge.points} pts</Badge>
                </div>
                <p className="text-xs text-slate-600">{challenge.category}</p>
                <p className="mt-2 text-xs text-slate-700">
                  flag regex: <code>{challenge.flag_regex ?? selectedCtf?.default_flag_regex ?? "(none)"}</code>
                </p>
                <p className="mt-2 text-xs text-slate-600">synced: {formatSyncedAt(challenge.synced_at)}</p>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <span className="rounded bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700">{runStats.total} runs</span>
                  {runStats.active > 0 ? (
                    <span className="rounded bg-blue-100 px-2 py-1 text-[11px] font-semibold text-blue-800">{runStats.active} active</span>
                  ) : null}
                  {runStats.deliverablesProduced > 0 ? (
                    <span className="rounded bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-800">
                      deliverables_produced {runStats.deliverablesProduced}
                    </span>
                  ) : null}
                  {runStats.flagFound > 0 ? (
                    <span className="rounded bg-emerald-100 px-2 py-1 text-[11px] font-semibold text-emerald-800">flag_found {runStats.flagFound}</span>
                  ) : null}
                  {runStats.blockedOrTimeout > 0 ? (
                    <span className="rounded bg-rose-100 px-2 py-1 text-[11px] font-semibold text-rose-800">
                      blocked/timeout {runStats.blockedOrTimeout}
                    </span>
                  ) : null}
                </div>

                <div className="mt-3 flex items-center justify-between">
                  <Link className="text-xs font-semibold text-accent hover:underline" to={`/challenges/${challenge.id}`}>
                    Open
                  </Link>
                  <button
                    type="button"
                    className="text-xs font-semibold text-danger hover:underline"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (!window.confirm(`Delete challenge '${challenge.name}'?`)) {
                        return;
                      }
                      deleteMutation.mutate(challenge.id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        {deleteMutation.isError ? <p className="mt-3 text-sm text-danger">Failed to delete challenge.</p> : null}
      </Card>

      <div className="space-y-4">
        <Card>
          <h3 className="mb-1 text-lg font-semibold">Add Challenge</h3>
          <p className="mb-3 text-sm text-slate-600">
            New challenge for <span className="font-semibold">{selectedCtf?.name ?? "selected CTF"}</span>.
          </p>
          <form
            className="space-y-3"
            onSubmit={form.handleSubmit((values) => {
              createMutation.mutate(values);
            })}
          >
            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="name">
                Name
              </label>
              <input id="name" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("name")} />
              {form.formState.errors.name ? <p className="mt-1 text-xs text-danger">{form.formState.errors.name.message}</p> : null}
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="category">
                Category
              </label>
              <input id="category" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("category")} />
              {form.formState.errors.category ? <p className="mt-1 text-xs text-danger">{form.formState.errors.category.message}</p> : null}
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="points">
                Points
              </label>
              <input id="points" type="number" min={0} className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("points")} />
              {form.formState.errors.points ? <p className="mt-1 text-xs text-danger">{form.formState.errors.points.message}</p> : null}
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="description_md">
                Description
              </label>
              <textarea
                id="description_md"
                className="min-h-32 w-full rounded-md border border-slate-300 px-3 py-2"
                {...form.register("description_md")}
              />
              {form.formState.errors.description_md ? <p className="mt-1 text-xs text-danger">{form.formState.errors.description_md.message}</p> : null}
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium" htmlFor="flag_regex">
                Challenge Flag Regex Override
              </label>
              <input id="flag_regex" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("flag_regex")} />
              <p className="mt-1 text-xs text-slate-600">Leave blank to inherit the CTF default regex.</p>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium">Artifacts</label>
              <ArtifactDropzone disabled={uploadArtifactMutation.isPending} onFilesSelected={onArtifactFilesSelected} />
              {uploadArtifactMutation.isPending ? <p className="mt-1 text-xs text-slate-600">Uploading artifact...</p> : null}
              {uploadArtifactMutation.isError ? <p className="mt-1 text-xs text-danger">Failed to upload one or more artifacts.</p> : null}

              {artifacts.length > 0 ? (
                <ul className="mt-3 space-y-2 text-sm">
                  {artifacts.map((artifact) => (
                    <li key={artifact.object_key} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2">
                      <span>
                        {artifact.name} <span className="text-xs text-slate-500">({artifact.size_bytes} bytes)</span>
                      </span>
                      <button
                        type="button"
                        className="text-xs font-semibold text-danger hover:underline"
                        onClick={() => {
                          setArtifacts((previous) => previous.filter((item) => item.object_key !== artifact.object_key));
                        }}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-slate-600">No artifacts attached.</p>
              )}
            </div>

            {createMutation.isError ? <p className="text-sm text-danger">Failed to create challenge.</p> : null}

            <Button type="submit" className="w-full" disabled={createMutation.isPending || uploadArtifactMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create Challenge"}
            </Button>
          </form>
        </Card>

        <CTFdImportCard />
      </div>
    </div>
  );
}
