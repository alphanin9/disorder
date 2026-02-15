import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { RunsPage } from "@/features/runs/RunsPage";

const activeRun = {
  id: "7d2d5201-08e5-4450-bbe3-0d27d2916659",
  challenge_id: "11e0d301-3635-497c-990a-2a11721022a0",
  backend: "codex",
  budgets: { max_minutes: 30, max_commands: null },
  stop_criteria: {},
  allowed_endpoints: [],
  paths: { chal_mount: "/workspace/chal", run_mount: "/workspace/run" },
  local_deploy: { enabled: false, network: null, endpoints: [] },
  status: "running",
  error_message: null,
  started_at: "2026-02-14T22:00:00Z",
  finished_at: null,
};

const server = setupServer(
  http.get("http://localhost/api/runs", ({ request }) => {
    const url = new URL(request.url);
    if (url.searchParams.get("active_only") === "true") {
      return HttpResponse.json({ items: [activeRun] });
    }
    return HttpResponse.json({ items: [activeRun] });
  }),
  http.get("http://localhost/api/challenges", () =>
    HttpResponse.json({
      items: [
        {
          id: "11e0d301-3635-497c-990a-2a11721022a0",
          ctf_id: "11111111-1111-1111-1111-111111111111",
          ctf_name: "Demo CTF",
          platform: "manual",
          platform_challenge_id: "manual-1",
          name: "Warmup",
          category: "misc",
          points: 100,
          description_md: "",
          description_raw: "",
          artifacts: [],
          remote_endpoints: [],
          local_deploy_hints: {},
          flag_regex: null,
          synced_at: "2026-02-14T22:00:00Z",
        },
      ],
    }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("RunsPage", () => {
  it("renders active runs", async () => {
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
        <MemoryRouter initialEntries={["/runs"]}>
          <Routes>
            <Route path="/runs" element={<RunsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Active Agent Runner Instances/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/Warmup/i)).length).toBeGreaterThan(0);
    expect(await screen.findByRole("cell", { name: /running/i })).toBeInTheDocument();
  });
});
