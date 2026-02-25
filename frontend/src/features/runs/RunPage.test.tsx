import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

import { RunPage } from "@/features/runs/RunPage";

const server = setupServer(
  http.get("http://localhost/api/runs/:run_id", ({ params }) =>
    HttpResponse.json({
      run: {
        id: params.run_id,
        challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
        backend: "mock",
        budgets: { max_minutes: 30, max_commands: null },
        stop_criteria: {},
        allowed_endpoints: [],
        paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
        local_deploy: { enabled: false, network: null, endpoints: [] },
        status: "deliverable_produced",
        error_message: null,
        started_at: "2026-02-14T22:00:00Z",
        finished_at: "2026-02-14T22:01:00Z",
        parent_run_id: null,
        continuation_depth: 0,
        continuation_input: null,
        continuation_type: null,
      },
      result: null,
      child_runs: [
        {
          id: "f3325e1f-0a77-42fc-a8e0-607fcfcb00f2",
          challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
          backend: "mock",
          budgets: { max_minutes: 30, max_commands: null },
          stop_criteria: {},
          allowed_endpoints: [],
          paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
          local_deploy: { enabled: false, network: null, endpoints: [] },
          status: "queued",
          error_message: null,
          started_at: "2026-02-14T22:02:00Z",
          finished_at: null,
          parent_run_id: params.run_id,
          continuation_depth: 1,
          continuation_input: "retry",
          continuation_type: "hint",
        },
      ],
    }),
  ),
  http.get("http://localhost/api/runs/:run_id/logs", () =>
    HttpResponse.json({ run_id: "r", offset: 0, next_offset: 0, eof: true, logs: "" }),
  ),
  http.get("http://localhost/api/runs/:run_id/result", () =>
    HttpResponse.json({
      challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
      challenge_name: "Warmup",
      status: "deliverable_produced",
      stop_criterion_met: "secondary",
      flag_verification: { method: "none", verified: false, details: "mock" },
      deliverables: [{ path: "solve.py", type: "solve_script", how_to_run: "python solve.py" }],
      repro_steps: ["run solve"],
      key_findings: ["mock"],
      evidence: [{ kind: "file", ref: "solve.py", summary: "present" }],
      notes: "ok",
    }),
  ),
  http.get("http://localhost/api/challenges/:challenge_id", ({ params }) =>
    HttpResponse.json({
      id: params.challenge_id,
      ctf_id: "11111111-1111-1111-1111-111111111111",
      ctf_name: "Demo CTF",
      name: "Warmup",
      category: "misc",
      points: 50,
      description_md: "Demo",
      description_raw: null,
      flag_regex: null,
      platform: "manual",
      platform_challenge_id: "warmup-1",
      local_deploy_hints: {},
      remote_endpoints: [],
      artifacts: [],
      synced_at: "2026-02-14T22:00:00Z",
    }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("RunPage", () => {
  it("renders terminal result", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/runs/7d2d5201-08e5-4450-bbe3-0d27d2916659"]}>
          <Routes>
            <Route path="/runs/:runId" element={<RunPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Run 7d2d5201/i)).toBeInTheDocument();
    expect(await screen.findByText("Challenge / CTF")).toBeInTheDocument();
    expect(await screen.findByText("Warmup / Demo CTF")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Continue run/i })).toBeInTheDocument();
    expect(await screen.findByText(/Child runs/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("secondary")).toBeInTheDocument();
    });
  });

  it("hides continue action for non-terminal runs", async () => {
    server.use(
      http.get("http://localhost/api/runs/:run_id", ({ params }) =>
        HttpResponse.json({
          run: {
            id: params.run_id,
            challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
            backend: "mock",
            budgets: { max_minutes: 30, max_commands: null },
            stop_criteria: {},
            allowed_endpoints: [],
            paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
            local_deploy: { enabled: false, network: null, endpoints: [] },
            status: "running",
            error_message: null,
            started_at: "2026-02-14T22:00:00Z",
            finished_at: null,
            parent_run_id: null,
            continuation_depth: 0,
            continuation_input: null,
            continuation_type: null,
          },
          result: null,
          child_runs: [],
        }),
      ),
    );

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          refetchInterval: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/runs/7d2d5201-08e5-4450-bbe3-0d27d2916659"]}>
          <Routes>
            <Route path="/runs/:runId" element={<RunPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Run 7d2d5201/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Continue run/i })).not.toBeInTheDocument();
    });
  });

  it("resets log polling offset when navigating to another run", async () => {
    const logRequests: Array<{ runId: string; offset: number }> = [];

    server.use(
      http.get("http://localhost/api/runs/:run_id/logs", ({ params, request }) => {
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get("offset") ?? "0");
        const runId = String(params.run_id);
        logRequests.push({ runId, offset });
        return HttpResponse.json({
          run_id: runId,
          offset,
          next_offset: runId.startsWith("7d2d") ? 5 : 0,
          eof: true,
          logs: "",
        });
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          refetchInterval: false,
        },
      },
    });

    function TestShell() {
      const navigate = useNavigate();
      return (
        <>
          <button type="button" onClick={() => navigate("/runs/f3325e1f-0a77-42fc-a8e0-607fcfcb00f2")}>
            Navigate
          </button>
          <Routes>
            <Route path="/runs/:runId" element={<RunPage />} />
          </Routes>
        </>
      );
    }

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/runs/7d2d5201-08e5-4450-bbe3-0d27d2916659"]}>
          <TestShell />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Run 7d2d5201/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(logRequests).toContainEqual({
        runId: "7d2d5201-08e5-4450-bbe3-0d27d2916659",
        offset: 0,
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "Navigate" }));

    await waitFor(() => {
      expect(logRequests).toContainEqual({
        runId: "f3325e1f-0a77-42fc-a8e0-607fcfcb00f2",
        offset: 0,
      });
    });
  });
});
