import { apiRequest } from "@/api/client";
import type {
  ChallengeCreateRequest,
  ChallengeArtifact,
  ChallengeListResponse,
  ChallengeManifest,
  ChallengeUpdateRequest,
  CodexAuthFile,
  CodexAuthStatusResponse,
  CTF,
  CTFCreateRequest,
  CTFListResponse,
  CTFUpdateRequest,
  RunCreateRequest,
  RunListResponse,
  RunLogsResponse,
  RunRead,
  RunResultPayload,
  RunStatusResponse,
} from "@/api/models";

export async function getChallenges(): Promise<ChallengeListResponse> {
  return apiRequest<ChallengeListResponse>("/challenges");
}

export async function getChallenge(challengeId: string): Promise<ChallengeManifest> {
  return apiRequest<ChallengeManifest>(`/challenges/${challengeId}`);
}

export async function createChallenge(payload: ChallengeCreateRequest): Promise<ChallengeManifest> {
  return apiRequest<ChallengeManifest>("/challenges", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateChallenge(challengeId: string, payload: ChallengeUpdateRequest): Promise<ChallengeManifest> {
  return apiRequest<ChallengeManifest>(`/challenges/${challengeId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function uploadChallengeArtifact(file: File): Promise<ChallengeArtifact> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<ChallengeArtifact>("/challenges/artifacts/upload", {
    method: "POST",
    body: formData,
  });
}

export async function getCtfs(): Promise<CTFListResponse> {
  return apiRequest<CTFListResponse>("/ctfs");
}

export async function createCtf(payload: CTFCreateRequest): Promise<CTF> {
  return apiRequest<CTF>("/ctfs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateCtf(ctfId: string, payload: CTFUpdateRequest): Promise<CTF> {
  return apiRequest<CTF>(`/ctfs/${ctfId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function createRun(payload: RunCreateRequest): Promise<RunRead> {
  return apiRequest<RunRead>("/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getRuns(options?: { status?: string[]; challengeId?: string; activeOnly?: boolean; limit?: number }): Promise<RunListResponse> {
  const params = new URLSearchParams();
  if (options?.activeOnly) {
    params.set("active_only", "true");
  }
  if (options?.challengeId) {
    params.set("challenge_id", options.challengeId);
  }
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  for (const status of options?.status ?? []) {
    params.append("status", status);
  }
  const suffix = params.toString();
  return apiRequest<RunListResponse>(`/runs${suffix ? `?${suffix}` : ""}`);
}

export async function getRun(runId: string): Promise<RunStatusResponse> {
  return apiRequest<RunStatusResponse>(`/runs/${runId}`);
}

export async function getRunLogs(runId: string, offset: number, limit = 65536): Promise<RunLogsResponse> {
  return apiRequest<RunLogsResponse>(`/runs/${runId}/logs?offset=${offset}&limit=${limit}`);
}

export async function getRunResult(runId: string): Promise<RunResultPayload> {
  return apiRequest<RunResultPayload>(`/runs/${runId}/result`);
}

export async function getCodexAuthStatus(): Promise<CodexAuthStatusResponse> {
  return apiRequest<CodexAuthStatusResponse>("/auth/codex/status");
}

export async function uploadCodexAuthFile(file: File, tag: string): Promise<CodexAuthFile> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("tag", tag);
  return apiRequest<CodexAuthFile>("/auth/codex/files", {
    method: "POST",
    body: formData,
  });
}

export async function setCodexAuthActiveTag(tag: string): Promise<CodexAuthStatusResponse> {
  return apiRequest<CodexAuthStatusResponse>("/auth/codex/active-tag", {
    method: "POST",
    body: JSON.stringify({ tag }),
  });
}

export async function deleteCodexAuthFile(fileId: string): Promise<CodexAuthStatusResponse> {
  return apiRequest<CodexAuthStatusResponse>(`/auth/codex/files/${fileId}`, {
    method: "DELETE",
  });
}

export async function deleteCodexAuthTag(tag: string): Promise<CodexAuthStatusResponse> {
  return apiRequest<CodexAuthStatusResponse>(`/auth/codex/tags/${encodeURIComponent(tag)}`, {
    method: "DELETE",
  });
}
