import { apiRequest } from "@/api/client";
import type {
  ChallengeListResponse,
  ChallengeManifest,
  RunCreateRequest,
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

export async function createRun(payload: RunCreateRequest): Promise<RunRead> {
  return apiRequest<RunRead>("/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
