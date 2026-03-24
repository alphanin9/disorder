import type { components } from "@/api/types";

export type ChallengeManifest = components["schemas"]["ChallengeManifestRead"];
export type ChallengeListResponse = components["schemas"]["ChallengeListResponse"];
export type AgentInvocationPayload = {
  model?: string | null;
  profile?: string | null;
  extra_args?: string[];
  env?: Record<string, string>;
};
export type AutoContinuationPolicyPayload = {
  enabled?: boolean;
  max_depth?: number;
  target?: {
    final_status?: "flag_found" | "deliverable_produced" | "blocked" | "timeout";
  };
  when?: {
    statuses?: Array<"flag_found" | "deliverable_produced" | "blocked" | "timeout">;
    require_contract_match?: boolean;
  };
  on_blocked_reasons?: string[];
  continuation_type?: "hint" | "deliverable_fix" | "strategy_change" | "other";
  message_template?: string;
  inherit_agent_invocation?: boolean;
};
export type RunnerLoopPolicyPayload = {
  enabled?: boolean;
  max_attempts?: number;
  target_status?: "flag_found" | "deliverable_produced" | "blocked";
  retry_on_statuses?: Array<"flag_found" | "deliverable_produced" | "blocked">;
  retry_on_reason_codes?: string[];
  continue_on_partial_success?: boolean;
  min_seconds_remaining?: number;
  instruction_template?: string;
};
type BaseRunCreateRequest = components["schemas"]["RunCreateRequest"];
export type RunCreateRequest = BaseRunCreateRequest & {
  reasoning_effort?: "low" | "medium" | "high" | "xhigh";
  budgets?: {
    max_minutes: number;
    max_commands?: number | null;
  } | null;
  agent_invocation?: AgentInvocationPayload | null;
  auto_continuation_policy?: AutoContinuationPolicyPayload | null;
  runner_loop_policy?: RunnerLoopPolicyPayload | null;
};
export type RunContinuationType = "hint" | "deliverable_fix" | "strategy_change" | "other";
type BaseRunRead = components["schemas"]["RunRead"];
export type RunRead = BaseRunRead & {
  parent_run_id?: string | null;
  continuation_depth?: number;
  continuation_input?: string | null;
  continuation_type?: RunContinuationType | null;
  continuation_origin?: "operator" | "auto";
  agent_invocation?: AgentInvocationPayload;
  auto_continuation_policy?: AutoContinuationPolicyPayload | null;
  runner_loop_policy?: RunnerLoopPolicyPayload | null;
};
export type RunListResponse = { items: RunRead[] };
type BaseRunResultRead = components["schemas"]["RunResultRead"];
export type RunResultRead = BaseRunResultRead & {
  finalization_metadata?: {
    contract_valid?: boolean;
    sandbox_exit_code?: number | null;
    timed_out?: boolean;
    result_status_before_stop_eval?: string;
    result_status_after_stop_eval?: string;
    failure_reason_code?: string;
    failure_reason_detail?: string;
    runner_loop?: {
      policy?: RunnerLoopPolicyPayload;
      total_attempts?: number;
      final_attempt_number?: number | null;
      stopped_because?: string | null;
      attempts?: Array<{
        attempt: number;
        status: string;
        failure_reason_code: string;
        backend_exit_code: number;
        contract_exit_code?: number;
        decision: string;
        decision_reason: string;
        remaining_seconds_after_attempt?: number;
        snapshot_dir?: string;
        deliverables_manifest_path?: string;
        last_message_path?: string | null;
      }>;
    };
  } | null;
};
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
  agent_invocation_override?: AgentInvocationPayload | null;
  auto_continuation_policy_override?: AutoContinuationPolicyPayload | null;
};
export type CTF = components["schemas"]["CTFRead"];
export type CTFListResponse = components["schemas"]["CTFListResponse"];
export type CTFCreateRequest = components["schemas"]["CTFCreateRequest"];
export type CTFUpdateRequest = components["schemas"]["CTFUpdateRequest"];
export type CTFdConfigResponse = components["schemas"]["CTFdConfigResponse"];
export type CTFdPerCtfConfigResponse = {
  base_url: string;
  configured: boolean;
  preferred_auth_mode?: "session_cookie" | "api_token" | null;
  has_api_token: boolean;
  has_session_cookie: boolean;
  stored_auth_modes: Array<"session_cookie" | "api_token">;
  last_sync_auth_mode?: "session_cookie" | "api_token" | null;
  last_submit_auth_mode?: "session_cookie" | "api_token" | null;
  last_submit_status?: string | null;
  updated_at?: string | null;
};
type BaseCTFdSyncRequest = components["schemas"]["CTFdSyncRequest"];
export type CTFdSyncRequest = BaseCTFdSyncRequest & {
  auth_mode?: "session_cookie" | "api_token" | null;
  session_cookie?: string | null;
};
export type CTFdSyncResponse = {
  synced: number;
  platform: string;
  ctf_id: string;
  ctf_slug: string;
  auth_mode_used: "session_cookie" | "api_token";
  stored_auth_modes: Array<"session_cookie" | "api_token">;
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
  failure_reason_code?: string;
  failure_reason_detail?: string;
};

export type RunFlagSubmissionAttempt = {
  id: string;
  run_id: string;
  challenge_id: string;
  platform: string;
  auth_mode?: string | null;
  submission_hash: string;
  verdict_normalized: string;
  http_status?: number | null;
  error_message?: string | null;
  submitted_at: string;
};

export type RunFlagSubmissionListResponse = {
  items: RunFlagSubmissionAttempt[];
};
