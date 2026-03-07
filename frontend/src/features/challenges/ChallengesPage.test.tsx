import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { fireEvent, screen } from "@testing-library/react";

import { ChallengesPage } from "@/features/challenges/ChallengesPage";
import { renderWithProviders } from "@/test/render";

const server = setupServer(
  http.get("http://localhost/api/challenges", () =>
    HttpResponse.json({
      items: [
        {
          id: "11e0d301-3635-497c-990a-2a11721022a0",
          ctf_id: "26eb88c7-6cb6-4b04-875a-ef2d8d71a70f",
          ctf_name: "Disorder CTF",
          platform: "ctfd",
          platform_challenge_id: "1",
          name: "Warmup",
          category: "misc",
          points: 50,
          description_md: "Find the flag",
          description_raw: "Find the flag",
          artifacts: [],
          remote_endpoints: [],
          local_deploy_hints: { compose_present: false, notes: null },
          flag_regex: "flag\\{.*?\\}",
          synced_at: "2026-02-14T22:00:00Z",
        },
      ],
    }),
  ),
  http.get("http://localhost/api/runs", ({ request }) => {
    const challengeId = new URL(request.url).searchParams.get("challenge_id");
    if (challengeId !== "11e0d301-3635-497c-990a-2a11721022a0") {
      return HttpResponse.json({ items: [] });
    }
    return HttpResponse.json({
      items: [
        {
          id: "7d2d5201-08e5-4450-bbe3-0d27d2916651",
          challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
          backend: "codex",
          budgets: { max_minutes: 30, max_commands: null },
          stop_criteria: {},
          allowed_endpoints: [],
          paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
          local_deploy: { enabled: false, network: null, endpoints: [] },
          status: "flag_found",
          error_message: null,
          started_at: "2026-02-14T22:00:00Z",
          finished_at: "2026-02-14T22:01:00Z",
        },
        {
          id: "7d2d5201-08e5-4450-bbe3-0d27d2916652",
          challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
          backend: "codex",
          budgets: { max_minutes: 30, max_commands: null },
          stop_criteria: {},
          allowed_endpoints: [],
          paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
          local_deploy: { enabled: false, network: null, endpoints: [] },
          status: "deliverable_produced",
          error_message: null,
          started_at: "2026-02-14T22:02:00Z",
          finished_at: "2026-02-14T22:03:00Z",
        },
        {
          id: "7d2d5201-08e5-4450-bbe3-0d27d2916653",
          challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
          backend: "codex",
          budgets: { max_minutes: 30, max_commands: null },
          stop_criteria: {},
          allowed_endpoints: [],
          paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
          local_deploy: { enabled: false, network: null, endpoints: [] },
          status: "blocked",
          error_message: "blocked",
          started_at: "2026-02-14T22:04:00Z",
          finished_at: "2026-02-14T22:05:00Z",
        },
        {
          id: "7d2d5201-08e5-4450-bbe3-0d27d2916654",
          challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
          backend: "codex",
          budgets: { max_minutes: 30, max_commands: null },
          stop_criteria: {},
          allowed_endpoints: [],
          paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
          local_deploy: { enabled: false, network: null, endpoints: [] },
          status: "running",
          error_message: null,
          started_at: "2026-02-14T22:06:00Z",
          finished_at: null,
        },
      ],
    });
  }),
  http.get("http://localhost/api/ctfs", () =>
    HttpResponse.json({
      items: [
        {
          id: "26eb88c7-6cb6-4b04-875a-ef2d8d71a70f",
          name: "Disorder CTF",
          slug: "disorder-ctf",
          platform: "manual",
          default_flag_regex: "flag\\{.*?\\}",
          notes: null,
          created_at: "2026-02-14T22:00:00Z",
          updated_at: "2026-02-14T22:00:00Z",
        },
      ],
    }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ChallengesPage", () => {
  it("opens a CTF card into a challenge grid and keeps sync available", async () => {
    renderWithProviders(<ChallengesPage />);

    expect(await screen.findByRole("heading", { level: 2, name: "CTF Events" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /disorder ctf/i }));

    expect(await screen.findByText("Warmup")).toBeInTheDocument();
    expect(screen.getByText("misc")).toBeInTheDocument();
    expect(screen.getByText("50 pts")).toBeInTheDocument();
    expect(await screen.findByText("4 runs")).toBeInTheDocument();
    expect(screen.getByText("1 active")).toBeInTheDocument();
    expect(screen.getByText("deliverables_produced 1")).toBeInTheDocument();
    expect(screen.getByText("flag_found 1")).toBeInTheDocument();
    expect(screen.getByText("blocked/timeout 1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Import from CTFd" })).toBeInTheDocument();
  });
});
