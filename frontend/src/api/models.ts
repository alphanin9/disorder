import type { components } from "@/api/types";

export type ChallengeManifest = components["schemas"]["ChallengeManifestRead"];
export type ChallengeListResponse = components["schemas"]["ChallengeListResponse"];
export type RunCreateRequest = components["schemas"]["RunCreateRequest"];
export type RunRead = components["schemas"]["RunRead"];
export type RunListResponse = { items: RunRead[] };
export type RunStatusResponse = components["schemas"]["RunStatusResponse"];
export type RunLogsResponse = components["schemas"]["RunLogsResponse"];
export type CTF = components["schemas"]["CTFRead"];
export type CTFListResponse = components["schemas"]["CTFListResponse"];
export type CTFCreateRequest = components["schemas"]["CTFCreateRequest"];
export type CTFUpdateRequest = components["schemas"]["CTFUpdateRequest"];
export type ChallengeCreateRequest = components["schemas"]["ChallengeCreateRequest"];
export type ChallengeUpdateRequest = components["schemas"]["ChallengeUpdateRequest"];
export type ChallengeArtifact = components["schemas"]["ChallengeArtifactRead"];

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
