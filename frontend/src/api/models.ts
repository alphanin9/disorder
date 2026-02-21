import type { components } from "@/api/types";

export type ChallengeManifest = components["schemas"]["ChallengeManifestRead"];
export type ChallengeListResponse = components["schemas"]["ChallengeListResponse"];
type BaseRunCreateRequest = components["schemas"]["RunCreateRequest"];
export type RunCreateRequest = BaseRunCreateRequest & {
  reasoning_effort?: "low" | "medium" | "high" | "xhigh";
  budgets?: {
    max_minutes: number;
    max_commands?: number | null;
  } | null;
};
export type RunContinuationType = "hint" | "deliverable_fix" | "strategy_change" | "other";
type BaseRunRead = components["schemas"]["RunRead"];
export type RunRead = BaseRunRead & {
  parent_run_id?: string | null;
  continuation_depth?: number;
  continuation_input?: string | null;
  continuation_type?: RunContinuationType | null;
};
export type RunListResponse = { items: RunRead[] };
type BaseRunResultRead = components["schemas"]["RunResultRead"];
export type RunResultRead = BaseRunResultRead;
export type RunStatusResponse = {
  run: RunRead;
  result?: RunResultRead | null;
  child_runs?: RunRead[];
};
export type RunLogsResponse = components["schemas"]["RunLogsResponse"];
export type RunContinueRequest = {
  message: string;
  type?: RunContinuationType | null;
  time_limit_seconds?: number | null;
  stop_criteria_override?: Record<string, unknown> | null;
  reuse_parent_artifacts?: boolean;
};
export type CTF = components["schemas"]["CTFRead"];
export type CTFListResponse = components["schemas"]["CTFListResponse"];
export type CTFCreateRequest = components["schemas"]["CTFCreateRequest"];
export type CTFUpdateRequest = components["schemas"]["CTFUpdateRequest"];
export type CTFdConfigResponse = components["schemas"]["CTFdConfigResponse"];
type BaseCTFdSyncRequest = components["schemas"]["CTFdSyncRequest"];
export type CTFdSyncRequest = BaseCTFdSyncRequest & {
  auth_mode?: "session_cookie" | "api_token" | null;
  session_cookie?: string | null;
};
export type CTFdSyncResponse = {
  synced: number;
  platform: string;
};
export type ChallengeCreateRequest = components["schemas"]["ChallengeCreateRequest"];
export type ChallengeUpdateRequest = components["schemas"]["ChallengeUpdateRequest"];
export type ChallengeArtifact = components["schemas"]["ChallengeArtifactRead"];

export type CodexAuthFile = {
  id: string;
  tag: string;
  file_name: string;
  sha256: string;
  size_bytes: number;
  uploaded_at: string;
};

export type CodexAuthTag = {
  tag: string;
  file_count: number;
  files: CodexAuthFile[];
};

export type CodexAuthStatusResponse = {
  configured: boolean;
  active_tag: string | null;
  tags: CodexAuthTag[];
};

export type RunResultPayload = {
  challenge_id: string;
  challenge_name: string;
  status: "flag_found" | "deliverable_produced" | "blocked";
  stop_criterion_met: "primary" | "secondary" | "none";
  flag?: string;
  flag_verification: {
    method: "platform_submit" | "local_check" | "regex_only" | "none";
    verified: boolean;
    details: string;
  };
  deliverables: Array<{ path: string; type: string; how_to_run: string }>;
  repro_steps: string[];
  key_findings: string[];
  evidence: Array<{ kind: string; ref: string; summary: string }>;
  notes: string;
};
