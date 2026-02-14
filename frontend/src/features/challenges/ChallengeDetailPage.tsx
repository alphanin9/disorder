import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { createRun, getChallenge, getCtfs, updateChallenge } from "@/api/endpoints";
import type { RunCreateRequest } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const runSchema = z.object({
  backend: z.enum(["mock", "codex", "claude_code"]),
  local_deploy_enabled: z.boolean().default(false),
});

const editSchema = z.object({
  ctf_id: z.string().min(1, "CTF is required"),
  name: z.string().min(1, "Name is required"),
  category: z.string().min(1, "Category is required"),
  points: z.coerce.number().int().min(0),
  description_md: z.string().min(1, "Description is required"),
  flag_regex: z.string().optional(),
});

type RunForm = z.infer<typeof runSchema>;
type EditForm = z.infer<typeof editSchema>;

function normalizeOptional(value: string | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function ChallengeDetailPage() {
  const { challengeId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const challengeQuery = useQuery({
    queryKey: ["challenge", challengeId],
    queryFn: () => getChallenge(challengeId ?? ""),
    enabled: Boolean(challengeId),
  });

  const ctfQuery = useQuery({
    queryKey: ["ctfs"],
    queryFn: getCtfs,
  });

  const editForm = useForm<EditForm>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      ctf_id: "",
      name: "",
      category: "misc",
      points: 0,
      description_md: "",
      flag_regex: "",
    },
  });

  useEffect(() => {
    if (!challengeQuery.data) {
      return;
    }
    editForm.reset({
      ctf_id: challengeQuery.data.ctf_id,
      name: challengeQuery.data.name,
      category: challengeQuery.data.category,
      points: challengeQuery.data.points,
      description_md: challengeQuery.data.description_md,
      flag_regex: challengeQuery.data.flag_regex ?? "",
    });
  }, [challengeQuery.data, editForm]);

  const editMutation = useMutation({
    mutationFn: (values: EditForm) => {
      if (!challengeId) {
        throw new Error("Missing challenge id");
      }
      return updateChallenge(challengeId, {
        ctf_id: values.ctf_id,
        name: values.name.trim(),
        category: values.category.trim(),
        points: values.points,
        description_md: values.description_md,
        description_raw: values.description_md,
        flag_regex: normalizeOptional(values.flag_regex),
      });
    },
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["challenge", challengeId] }),
        queryClient.invalidateQueries({ queryKey: ["challenges"] }),
      ]);
    },
  });

  const runForm = useForm<RunForm>({
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
              {challengeQuery.data.ctf_name ?? "Unknown CTF"} | {challengeQuery.data.category} | {challengeQuery.data.points} pts
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

            <section className="mt-6">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Edit Challenge</h3>
              <form
                className="space-y-3"
                onSubmit={editForm.handleSubmit((values) => {
                  editMutation.mutate(values);
                })}
              >
                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="edit_ctf_id">
                    CTF
                  </label>
                  <select id="edit_ctf_id" className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("ctf_id")}>
                    <option value="">Select CTF</option>
                    {(ctfQuery.data?.items ?? []).map((ctf) => (
                      <option key={ctf.id} value={ctf.id}>
                        {ctf.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium" htmlFor="edit_name">
                      Name
                    </label>
                    <input id="edit_name" className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("name")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium" htmlFor="edit_category">
                      Category
                    </label>
                    <input id="edit_category" className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("category")} />
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="edit_points">
                    Points
                  </label>
                  <input id="edit_points" type="number" min={0} className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("points")} />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="edit_description_md">
                    Description
                  </label>
                  <textarea
                    id="edit_description_md"
                    className="min-h-28 w-full rounded-md border border-slate-300 px-3 py-2"
                    {...editForm.register("description_md")}
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="edit_flag_regex">
                    Challenge Flag Regex Override
                  </label>
                  <input id="edit_flag_regex" className="w-full rounded-md border border-slate-300 px-3 py-2" {...editForm.register("flag_regex")} />
                  <p className="mt-1 text-xs text-slate-600">Leave blank to inherit CTF default regex.</p>
                </div>

                {editMutation.isError ? <p className="text-sm text-danger">Failed to update challenge.</p> : null}
                {editMutation.isSuccess ? <p className="text-sm text-success">Challenge updated.</p> : null}

                <Button type="submit" disabled={editMutation.isPending}>
                  {editMutation.isPending ? "Saving..." : "Save Challenge"}
                </Button>
              </form>
            </section>
          </>
        ) : null}
      </Card>

      <Card>
        <h3 className="mb-3 text-lg font-semibold">Start Run</h3>
        <form
          className="space-y-4"
          onSubmit={runForm.handleSubmit((values) => {
            runMutation.mutate(values);
          })}
        >
          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="backend">
              Backend
            </label>
            <select id="backend" className="w-full rounded-md border border-slate-300 px-3 py-2" {...runForm.register("backend")}>
              <option value="mock">mock</option>
              <option value="codex">codex</option>
              <option value="claude_code">claude_code</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...runForm.register("local_deploy_enabled")} />
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
