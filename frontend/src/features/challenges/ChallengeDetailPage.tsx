import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { createRun, getChallenge, getCtfs, getRuns, updateChallenge, uploadChallengeArtifact } from "@/api/endpoints";
import type {
  AutoContinuationPolicyPayload,
  ChallengeArtifact,
  RunCreateRequest,
  RunnerLoopPolicyPayload,
} from "@/api/models";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { inputClasses } from "@/components/ui/forms";
import { ArtifactDropzone } from "@/features/challenges/ArtifactDropzone";
import { formatDateTime } from "@/features/runs/utils";

const AUTO_CONTINUATION_STATUSES = new Set(["blocked", "timeout", "flag_found", "deliverable_produced"] as const);
const RUNNER_LOOP_STATUSES = new Set(["blocked", "flag_found", "deliverable_produced"] as const);

const runSchema = z.object({
  backend: z.enum(["mock", "codex", "claude_code"]),
  reasoning_effort: z.enum(["low", "medium", "high", "xhigh"]),
  goal: z.enum(["flag", "deliverable"]),
  model: z.string().optional(),
  agent_invocation_json: z.string().optional(),
  auto_continue_enabled: z.boolean().default(false),
  auto_continue_max_depth: z.coerce.number().int().min(1).max(20).default(3),
  auto_continue_statuses: z.string().default("blocked,timeout"),
  auto_continue_reason_codes: z.string().default(""),
  runner_loop_enabled: z.boolean().default(false),
  runner_loop_max_attempts: z.coerce.number().int().min(1).max(20).default(3),
  runner_loop_retry_on_statuses: z.string().default("blocked"),
  runner_loop_reason_codes: z.string().default(""),
  runner_loop_continue_on_partial_success: z.boolean().default(true),
  runner_loop_min_seconds_remaining: z.coerce.number().int().min(0).max(24 * 60 * 60).default(120),
  runner_loop_instruction_template: z.string().optional(),
  local_deploy_enabled: z.boolean().default(false),
  max_minutes: z.coerce.number().int().min(1, "Must be at least 1 minute").max(24 * 60, "Must be <= 1440 minutes"),
  max_commands: z.preprocess(
    (value) => {
      if (typeof value === "string" && value.trim() === "") {
        return null;
      }
      return value;
    },
    z.coerce.number().int().min(1, "Must be >= 1 command").max(1_000_000, "Too large").nullable(),
  ),
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

function parseOptionalJsonObject(value: string | undefined, fieldName: string): Record<string, unknown> | undefined {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) {
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${fieldName} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${fieldName} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function parseArtifact(input: unknown): ChallengeArtifact | null {
  if (!input || typeof input !== "object") {
    return null;
  }
  const record = input as Record<string, unknown>;
  const name = typeof record.name === "string" ? record.name : null;
  const sha256 = typeof record.sha256 === "string" ? record.sha256 : null;
  const sizeBytes = typeof record.size_bytes === "number" ? record.size_bytes : null;
  const objectKey = typeof record.object_key === "string" ? record.object_key : null;
  if (!name || !sha256 || sizeBytes === null || !objectKey) {
    return null;
  }
  return { name, sha256, size_bytes: sizeBytes, object_key: objectKey };
}

export function ChallengeDetailPage() {
  const { challengeId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [artifacts, setArtifacts] = useState<ChallengeArtifact[]>([]);

  const challengeQuery = useQuery({
    queryKey: ["challenge", challengeId],
    queryFn: () => getChallenge(challengeId ?? ""),
    enabled: Boolean(challengeId),
  });

  const ctfQuery = useQuery({
    queryKey: ["ctfs"],
    queryFn: getCtfs,
  });

  const challengeRunsQuery = useQuery({
    queryKey: ["runs", "challenge", challengeId],
    queryFn: () => getRuns({ challengeId: challengeId ?? "", limit: 100 }),
    enabled: Boolean(challengeId),
    refetchInterval: 2000,
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
    setArtifacts(challengeQuery.data.artifacts.map(parseArtifact).filter((artifact): artifact is ChallengeArtifact => artifact !== null));
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
        artifacts,
        local_deploy_hints: {
          compose_present: artifacts.some((artifact) => ["docker-compose.yml", "compose.yml"].includes(artifact.name)),
          notes: null,
        },
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
      reasoning_effort: "medium",
      goal: "flag",
      model: "",
      agent_invocation_json: "",
      auto_continue_enabled: false,
      auto_continue_max_depth: 3,
      auto_continue_statuses: "blocked,timeout",
      auto_continue_reason_codes: "",
      runner_loop_enabled: false,
      runner_loop_max_attempts: 3,
      runner_loop_retry_on_statuses: "blocked",
      runner_loop_reason_codes: "",
      runner_loop_continue_on_partial_success: true,
      runner_loop_min_seconds_remaining: 120,
      runner_loop_instruction_template: "",
      local_deploy_enabled: false,
      max_minutes: 30,
      max_commands: null,
    },
  });

  const runMutation = useMutation({
    mutationFn: (values: RunForm) => {
      const stopCriteria =
        values.goal === "deliverable"
          ? {
              primary: {
                type: "DELIVERABLES_READY",
                config: {
                  required_files: ["README.md"],
                },
              },
              secondary: {
                type: "FLAG_FOUND",
                config: {},
              },
            }
          : {
              primary: {
                type: "FLAG_FOUND",
                config: {},
              },
              secondary: {
                type: "DELIVERABLES_READY",
                config: {
                  required_files: ["README.md"],
                },
              },
            };

      const parsedAgentInvocation = parseOptionalJsonObject(values.agent_invocation_json, "Agent invocation JSON");
      const model = values.model?.trim();
      const agentInvocation =
        parsedAgentInvocation || model
          ? {
              ...(parsedAgentInvocation ?? {}),
              ...(model ? { model } : {}),
            }
          : undefined;
      const autoContinuationPolicy: AutoContinuationPolicyPayload | undefined =
        values.auto_continue_enabled
          ? {
              enabled: true,
              max_depth: values.auto_continue_max_depth,
              target: {
                final_status: values.goal === "flag" ? "flag_found" : "deliverable_produced",
              },
              when: {
                statuses: values.auto_continue_statuses
                  .split(",")
                  .map((value) => value.trim())
                  .filter((value): value is "blocked" | "timeout" | "flag_found" | "deliverable_produced" =>
                    AUTO_CONTINUATION_STATUSES.has(value as "blocked" | "timeout" | "flag_found" | "deliverable_produced"),
                  ),
              },
              on_blocked_reasons: values.auto_continue_reason_codes
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
            }
          : undefined;
      const runnerLoopPolicy: RunnerLoopPolicyPayload | undefined =
        values.runner_loop_enabled
          ? {
              enabled: true,
              max_attempts: values.runner_loop_max_attempts,
              target_status: values.goal === "flag" ? "flag_found" : "deliverable_produced",
              retry_on_statuses: values.runner_loop_retry_on_statuses
                .split(",")
                .map((value) => value.trim())
                .filter((value): value is "blocked" | "flag_found" | "deliverable_produced" =>
                  RUNNER_LOOP_STATUSES.has(value as "blocked" | "flag_found" | "deliverable_produced"),
                ),
              retry_on_reason_codes: values.runner_loop_reason_codes
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
              continue_on_partial_success: values.runner_loop_continue_on_partial_success,
              min_seconds_remaining: values.runner_loop_min_seconds_remaining,
              ...(values.runner_loop_instruction_template?.trim()
                ? { instruction_template: values.runner_loop_instruction_template.trim() }
                : {}),
            }
          : undefined;

      const payload: RunCreateRequest = {
        challenge_id: challengeId ?? "",
        backend: values.backend,
        reasoning_effort: values.reasoning_effort,
        budgets: {
          max_minutes: values.max_minutes,
          max_commands: values.max_commands,
        },
        stop_criteria: stopCriteria,
        local_deploy_enabled: values.local_deploy_enabled,
        agent_invocation: agentInvocation,
        auto_continuation_policy: autoContinuationPolicy,
        runner_loop_policy: runnerLoopPolicy,
      };
      return createRun(payload);
    },
    onSuccess: (run) => {
      navigate(`/runs/${run.id}`);
    },
  });

  const uploadArtifactMutation = useMutation({
    mutationFn: uploadChallengeArtifact,
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

  const activeRuns = useMemo(
    () => (challengeRunsQuery.data?.items ?? []).filter((run) => run.status === "queued" || run.status === "running"),
    [challengeRunsQuery.data],
  );
  const finishedRuns = useMemo(
    () => (challengeRunsQuery.data?.items ?? []).filter((run) => !["queued", "running"].includes(run.status)),
    [challengeRunsQuery.data],
  );

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
            <p className="mt-1 text-sm text-ink-muted">
              {challengeQuery.data.ctf_name ?? "Unknown CTF"} | {challengeQuery.data.category} | {challengeQuery.data.points} pts
            </p>

            <section className="mt-6">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-subtle">Description</h3>
              <pre className="whitespace-pre-wrap rounded-lg bg-surface-muted p-3 text-sm leading-relaxed text-ink">
                {challengeQuery.data.description_md}
              </pre>
            </section>

            <section className="mt-6">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-subtle">Artifacts</h3>
              {artifacts.length === 0 ? <p className="text-sm text-ink-muted">No artifacts attached.</p> : null}
              <ul className="space-y-2 text-sm">
                {artifacts.map((artifact) => (
                  <li key={artifact.object_key} className="rounded-md bg-surface-muted px-3 py-2">
                    {artifact.name}
                  </li>
                ))}
              </ul>
            </section>

            <section className="mt-6">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-subtle">Edit Challenge</h3>
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
                  <select id="edit_ctf_id" className={inputClasses} {...editForm.register("ctf_id")}>
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
                    <input id="edit_name" className={inputClasses} {...editForm.register("name")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium" htmlFor="edit_category">
                      Category
                    </label>
                    <input id="edit_category" className={inputClasses} {...editForm.register("category")} />
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="edit_points">
                    Points
                  </label>
                  <input id="edit_points" type="number" min={0} className={inputClasses} {...editForm.register("points")} />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="edit_description_md">
                    Description
                  </label>
                  <textarea
                    id="edit_description_md"
                    className={`${inputClasses} min-h-28`}
                    {...editForm.register("description_md")}
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="edit_flag_regex">
                    Challenge Flag Regex Override
                  </label>
                  <input id="edit_flag_regex" className={inputClasses} {...editForm.register("flag_regex")} />
                  <p className="mt-1 text-xs text-ink-muted">Leave blank to inherit CTF default regex.</p>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium">Artifacts</label>
                  <ArtifactDropzone disabled={uploadArtifactMutation.isPending} onFilesSelected={onArtifactFilesSelected} />
                  {uploadArtifactMutation.isPending ? <p className="mt-1 text-xs text-ink-muted">Uploading artifact...</p> : null}
                  {uploadArtifactMutation.isError ? <p className="mt-1 text-xs text-danger">Failed to upload one or more artifacts.</p> : null}

                  {artifacts.length > 0 ? (
                    <ul className="mt-3 space-y-2 text-sm">
                      {artifacts.map((artifact) => (
                        <li key={artifact.object_key} className="flex items-center justify-between rounded-md bg-surface-muted px-3 py-2">
                          <span>
                            {artifact.name} <span className="text-xs text-ink-subtle">({artifact.size_bytes} bytes)</span>
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
                    <p className="mt-2 text-xs text-ink-muted">No artifacts attached.</p>
                  )}
                </div>

                {editMutation.isError ? <p className="text-sm text-danger">Failed to update challenge.</p> : null}
                {editMutation.isSuccess ? <p className="text-sm text-success">Challenge updated.</p> : null}

                <Button type="submit" disabled={editMutation.isPending || uploadArtifactMutation.isPending}>
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
            <select id="backend" className={inputClasses} {...runForm.register("backend")}>
              <option value="mock">mock</option>
              <option value="codex">codex</option>
              <option value="claude_code">claude_code</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="goal">
              Run Goal
            </label>
            <select id="goal" className={inputClasses} {...runForm.register("goal")}>
              <option value="flag">Keep going until flag is found</option>
              <option value="deliverable">Stop once a working artifact is produced</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="model">
              Model Override
            </label>
            <input id="model" className={inputClasses} placeholder="gpt-5.4" {...runForm.register("model")} />
            <p className="mt-1 text-xs text-ink-muted">Optional per-run backend model selection.</p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="agent_invocation_json">
              Agent Invocation JSON
            </label>
            <textarea
              id="agent_invocation_json"
              className={`${inputClasses} min-h-24 font-mono text-xs`}
              placeholder='{"extra_args":["--search","full"],"env":{"CODEX_BASE_URL":"https://api.example"}}'
              {...runForm.register("agent_invocation_json")}
            />
            <p className="mt-1 text-xs text-ink-muted">Advanced backend-specific overrides. Model field above wins if both are set.</p>
          </div>

          <div className="rounded-md border border-line bg-surface-muted p-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...runForm.register("auto_continue_enabled")} />
              Auto-continue until the selected goal is reached
            </label>
            {runForm.watch("auto_continue_enabled") ? (
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="auto_continue_max_depth">
                    Max Continuation Depth
                  </label>
                  <input
                    id="auto_continue_max_depth"
                    type="number"
                    min={1}
                    max={20}
                    className={inputClasses}
                    {...runForm.register("auto_continue_max_depth")}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="auto_continue_statuses">
                    Retry Statuses
                  </label>
                  <input
                    id="auto_continue_statuses"
                    className={inputClasses}
                    placeholder="blocked,timeout"
                    {...runForm.register("auto_continue_statuses")}
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="mb-1 block text-sm font-medium" htmlFor="auto_continue_reason_codes">
                    Failure Reason Codes
                  </label>
                  <input
                    id="auto_continue_reason_codes"
                    className={inputClasses}
                    placeholder="provider_quota_or_auth,sandbox_exit_nonzero"
                    {...runForm.register("auto_continue_reason_codes")}
                  />
                  <p className="mt-1 text-xs text-ink-muted">Optional. Leave blank to retry any selected status.</p>
                </div>
              </div>
            ) : null}
          </div>

          <div className="rounded-md border border-line bg-surface-muted p-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...runForm.register("runner_loop_enabled")} />
              Retry inside the same sandbox run
            </label>
            <p className="mt-1 text-xs text-ink-muted">
              Reuses the same writable workspace, snapshots each attempt under <code>/workspace/run/attempts</code>, and does not create child runs.
            </p>
            {runForm.watch("runner_loop_enabled") ? (
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="runner_loop_max_attempts">
                    Max Attempts
                  </label>
                  <input
                    id="runner_loop_max_attempts"
                    type="number"
                    min={1}
                    max={20}
                    className={inputClasses}
                    {...runForm.register("runner_loop_max_attempts")}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="runner_loop_retry_on_statuses">
                    Retry Statuses
                  </label>
                  <input
                    id="runner_loop_retry_on_statuses"
                    className={inputClasses}
                    placeholder="blocked"
                    {...runForm.register("runner_loop_retry_on_statuses")}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="runner_loop_reason_codes">
                    Failure Reason Codes
                  </label>
                  <input
                    id="runner_loop_reason_codes"
                    className={inputClasses}
                    placeholder="provider_quota_or_auth,result_validation_failed"
                    {...runForm.register("runner_loop_reason_codes")}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium" htmlFor="runner_loop_min_seconds_remaining">
                    Min Seconds Remaining
                  </label>
                  <input
                    id="runner_loop_min_seconds_remaining"
                    type="number"
                    min={0}
                    max={24 * 60 * 60}
                    className={inputClasses}
                    {...runForm.register("runner_loop_min_seconds_remaining")}
                  />
                </div>
                <label className="sm:col-span-2 flex items-center gap-2 text-sm">
                  <input type="checkbox" {...runForm.register("runner_loop_continue_on_partial_success")} />
                  Keep retrying after <code>deliverable_produced</code> when the goal is a flag
                </label>
                <div className="sm:col-span-2">
                  <label className="mb-1 block text-sm font-medium" htmlFor="runner_loop_instruction_template">
                    Retry Instruction Template
                  </label>
                  <textarea
                    id="runner_loop_instruction_template"
                    className={`${inputClasses} min-h-24 font-mono text-xs`}
                    placeholder="Previous attempt ended with status {status} and reason {failure_reason_code}. Reuse the existing workspace..."
                    {...runForm.register("runner_loop_instruction_template")}
                  />
                </div>
              </div>
            ) : null}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="reasoning_effort">
              Reasoning Level
            </label>
            <select id="reasoning_effort" className={inputClasses} {...runForm.register("reasoning_effort")}>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="xhigh">xhigh</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...runForm.register("local_deploy_enabled")} />
            Enable local deploy (if compose file present)
          </label>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="max_minutes">
              Max Runtime (minutes)
            </label>
            <input
              id="max_minutes"
              type="number"
              min={1}
              max={24 * 60}
              className={inputClasses}
              {...runForm.register("max_minutes")}
            />
            {runForm.formState.errors.max_minutes ? (
              <p className="mt-1 text-xs text-danger">{runForm.formState.errors.max_minutes.message}</p>
            ) : (
              <p className="mt-1 text-xs text-ink-muted">Hard timeout for the sandbox container.</p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="max_commands">
              Max Commands (optional)
            </label>
            <input
              id="max_commands"
              type="number"
              min={1}
              className={inputClasses}
              placeholder="Unlimited"
              {...runForm.register("max_commands")}
            />
            {runForm.formState.errors.max_commands ? (
              <p className="mt-1 text-xs text-danger">{runForm.formState.errors.max_commands.message}</p>
            ) : (
              <p className="mt-1 text-xs text-ink-muted">Leave blank for no command-count cap.</p>
            )}
          </div>

          {runMutation.isError ? <p className="text-sm text-danger">Failed to start run.</p> : null}

          <Button type="submit" className="w-full" disabled={runMutation.isPending}>
            {runMutation.isPending ? "Starting..." : "Start Run"}
          </Button>
        </form>

        <section className="mt-6 border-t border-line pt-4">
          <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-subtle">Runs for This Challenge</h4>
          {challengeRunsQuery.isLoading ? <p className="text-sm">Loading runs...</p> : null}
          {challengeRunsQuery.error ? <p className="text-sm text-danger">Failed to load challenge runs.</p> : null}

          <div className="space-y-3">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-subtle">Active</p>
              {activeRuns.length === 0 ? <p className="text-xs text-ink-muted">No active runs.</p> : null}
              <ul className="space-y-2">
                {activeRuns.map((run) => (
                  <li key={run.id} className="rounded-md bg-surface-muted px-3 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <Link className="font-semibold text-accent hover:underline" to={`/runs/${run.id}`}>
                        {run.id.slice(0, 8)}
                      </Link>
                      <Badge status={run.status}>{run.status}</Badge>
                    </div>
                    <p className="mt-1 text-ink-muted">
                      {run.backend} | started {formatDateTime(run.started_at)}
                    </p>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-subtle">Completed</p>
              {finishedRuns.length === 0 ? <p className="text-xs text-ink-muted">No completed runs yet.</p> : null}
              <ul className="max-h-60 space-y-2 overflow-auto">
                {finishedRuns.map((run) => (
                  <li key={run.id} className="rounded-md bg-surface-muted px-3 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <Link className="font-semibold text-accent hover:underline" to={`/runs/${run.id}`}>
                        {run.id.slice(0, 8)}
                      </Link>
                      <Badge status={run.status}>{run.status}</Badge>
                    </div>
                    <p className="mt-1 text-ink-muted">
                      {run.backend} | finished {formatDateTime(run.finished_at)}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </Card>
    </div>
  );
}
