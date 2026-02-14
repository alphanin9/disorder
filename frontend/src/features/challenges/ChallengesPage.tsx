import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { createChallenge, getChallenges, getCtfs } from "@/api/endpoints";
import type { CTF, ChallengeCreateRequest, ChallengeManifest } from "@/api/models";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const createChallengeSchema = z.object({
  ctf_id: z.string().min(1, "CTF is required"),
  name: z.string().min(1, "Name is required"),
  category: z.string().min(1, "Category is required"),
  points: z.coerce.number().int().min(0),
  description_md: z.string().min(1, "Description is required"),
  flag_regex: z.string().optional(),
});

type CreateChallengeValues = z.infer<typeof createChallengeSchema>;

function normalizeOptional(value: string | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function ChallengesPage() {
  const queryClient = useQueryClient();

  const challengeQuery = useQuery({
    queryKey: ["challenges"],
    queryFn: getChallenges,
  });

  const ctfQuery = useQuery({
    queryKey: ["ctfs"],
    queryFn: getCtfs,
  });

  const form = useForm<CreateChallengeValues>({
    resolver: zodResolver(createChallengeSchema),
    defaultValues: {
      ctf_id: "",
      name: "",
      category: "misc",
      points: 0,
      description_md: "",
      flag_regex: "",
    },
  });

  const createMutation = useMutation({
    mutationFn: (values: CreateChallengeValues) => {
      const payload: ChallengeCreateRequest = {
        ctf_id: values.ctf_id,
        name: values.name.trim(),
        category: values.category.trim(),
        points: values.points,
        description_md: values.description_md.trim(),
        description_raw: values.description_md.trim(),
        platform: "manual",
        artifacts: [],
        remote_endpoints: [],
        local_deploy_hints: {
          compose_present: false,
          notes: null,
        },
        flag_regex: normalizeOptional(values.flag_regex),
      };
      return createChallenge(payload);
    },
    onSuccess: () => {
      form.reset({
        ctf_id: "",
        name: "",
        category: "misc",
        points: 0,
        description_md: "",
        flag_regex: "",
      });
      void queryClient.invalidateQueries({ queryKey: ["challenges"] });
    },
  });

  const ctfById = useMemo(() => {
    const map = new Map<string, CTF>();
    for (const ctf of ctfQuery.data?.items ?? []) {
      map.set(ctf.id, ctf);
    }
    return map;
  }, [ctfQuery.data]);

  const groupedChallenges = useMemo(() => {
    const buckets = new Map<string, ChallengeManifest[]>();
    for (const challenge of challengeQuery.data?.items ?? []) {
      const key = challenge.ctf_id;
      const existing = buckets.get(key) ?? [];
      existing.push(challenge);
      buckets.set(key, existing);
    }

    return [...buckets.entries()]
      .map(([ctfId, items]) => {
        const ctf = ctfById.get(ctfId);
        const firstItem = items[0];
        return {
          ctfId,
          ctfName: ctf?.name ?? firstItem?.ctf_name ?? "Unknown CTF",
          ctfDefaultFlagRegex: ctf?.default_flag_regex ?? null,
          items: [...items].sort((a, b) => a.name.localeCompare(b.name)),
        };
      })
      .sort((a, b) => a.ctfName.localeCompare(b.ctfName));
  }, [challengeQuery.data, ctfById]);

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card>
        <h2 className="mb-1 text-lg font-bold">Challenges</h2>
        <p className="mb-5 text-sm text-slate-600">Challenges are grouped by CTF. Override flag regex per challenge only when needed.</p>

        {challengeQuery.isLoading || ctfQuery.isLoading ? <p>Loading challenges...</p> : null}
        {challengeQuery.error || ctfQuery.error ? <p className="text-danger">Failed to load challenges.</p> : null}

        {groupedChallenges.length === 0 ? <p className="text-sm text-slate-600">No challenges yet.</p> : null}

        <div className="space-y-4">
          {groupedChallenges.map((group) => (
            <div key={group.ctfId} className="rounded-lg border border-slate-200 p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-base font-bold">{group.ctfName}</h3>
                  <p className="text-xs text-slate-600">
                    Default flag regex: <code>{group.ctfDefaultFlagRegex ?? "(none)"}</code>
                  </p>
                </div>
                <Badge>{group.items.length} challenges</Badge>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-2 py-2">Name</th>
                      <th className="px-2 py-2">Category</th>
                      <th className="px-2 py-2">Points</th>
                      <th className="px-2 py-2">Flag Regex</th>
                      <th className="px-2 py-2">Synced</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map((challenge) => (
                      <tr key={challenge.id} className="border-b border-slate-100 last:border-b-0">
                        <td className="px-2 py-3 font-semibold">
                          <Link className="text-accent hover:underline" to={`/challenges/${challenge.id}`}>
                            {challenge.name}
                          </Link>
                        </td>
                        <td className="px-2 py-3">{challenge.category}</td>
                        <td className="px-2 py-3">{challenge.points}</td>
                        <td className="px-2 py-3">
                          <code>{challenge.flag_regex ?? group.ctfDefaultFlagRegex ?? "(none)"}</code>
                          {challenge.flag_regex ? <span className="ml-2 text-xs text-slate-500">(override)</span> : null}
                        </td>
                        <td className="px-2 py-3 text-slate-600">{new Date(challenge.synced_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h3 className="mb-3 text-lg font-semibold">Add Challenge</h3>
        <form
          className="space-y-3"
          onSubmit={form.handleSubmit((values) => {
            createMutation.mutate(values);
          })}
        >
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="ctf_id">
              CTF
            </label>
            <select id="ctf_id" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("ctf_id")}>
              <option value="">Select CTF</option>
              {(ctfQuery.data?.items ?? []).map((ctf) => (
                <option key={ctf.id} value={ctf.id}>
                  {ctf.name}
                </option>
              ))}
            </select>
            {form.formState.errors.ctf_id ? <p className="mt-1 text-xs text-danger">{form.formState.errors.ctf_id.message}</p> : null}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="name">
              Name
            </label>
            <input id="name" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("name")} />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="category">
              Category
            </label>
            <input id="category" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("category")} />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="points">
              Points
            </label>
            <input id="points" type="number" min={0} className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("points")} />
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
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="flag_regex">
              Challenge Flag Regex Override
            </label>
            <input id="flag_regex" className="w-full rounded-md border border-slate-300 px-3 py-2" {...form.register("flag_regex")} />
            <p className="mt-1 text-xs text-slate-600">Leave blank to inherit the CTF default regex.</p>
          </div>

          {ctfQuery.data && ctfQuery.data.items.length === 0 ? (
            <p className="text-sm text-warning">
              No CTFs configured yet. Create one on the <Link to="/ctfs" className="font-semibold underline">CTFs page</Link>.
            </p>
          ) : null}
          {createMutation.isError ? <p className="text-sm text-danger">Failed to create challenge.</p> : null}

          <Button type="submit" className="w-full" disabled={createMutation.isPending || (ctfQuery.data?.items.length ?? 0) === 0}>
            {createMutation.isPending ? "Creating..." : "Create Challenge"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
