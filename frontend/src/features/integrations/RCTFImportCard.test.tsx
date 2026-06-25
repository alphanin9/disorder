import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { RCTFImportCard } from "@/features/integrations/RCTFImportCard";
import { renderWithProviders } from "@/test/render";

let lastSyncPayload: unknown = null;

const server = setupServer(
  http.post("http://localhost/api/integrations/rctf/sync", async ({ request }) => {
    lastSyncPayload = await request.json();
    return HttpResponse.json({
      synced: 4,
      platform: "rctf",
      ctf_id: "11111111-1111-1111-1111-111111111111",
      ctf_slug: "rctf-example-com",
      has_team_token: true,
    });
  }),
  http.get("http://localhost/api/ctfs/11111111-1111-1111-1111-111111111111/integrations/rctf/config", () =>
    HttpResponse.json({
      base_url: "https://rctf.example.com",
      configured: true,
      has_team_token: true,
      last_submit_status: null,
      updated_at: "2026-02-26T00:00:00Z",
    }),
  ),
);

beforeAll(() => server.listen());
beforeEach(() => {
  lastSyncPayload = null;
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("RCTFImportCard", () => {
  it("syncs challenges with a team token", async () => {
    renderWithProviders(<RCTFImportCard />);

    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "https://rctf.example.com" },
    });
    fireEvent.change(screen.getByLabelText(/team token/i), {
      target: { value: "team-tok-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sync from rctf/i }));

    expect(await screen.findByText("Synced 4 challenges from rctf.")).toBeInTheDocument();
    expect(await screen.findByText(/Saved rCTF Auth/i)).toBeInTheDocument();
    expect(lastSyncPayload).toEqual({
      base_url: "https://rctf.example.com",
      team_token: "team-tok-123",
    });
  });

  it("validates required fields", async () => {
    renderWithProviders(<RCTFImportCard />);

    fireEvent.click(screen.getByRole("button", { name: /sync from rctf/i }));

    expect(await screen.findByText("Base URL is required")).toBeInTheDocument();
    expect(screen.getByText("Team token is required")).toBeInTheDocument();
  });

  it("shows backend errors", async () => {
    server.use(
      http.post("http://localhost/api/integrations/rctf/sync", () =>
        HttpResponse.json({ detail: "rCTF sync requires a team_token." }, { status: 400 }),
      ),
    );

    renderWithProviders(<RCTFImportCard />);

    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "https://rctf.example.com" },
    });
    fireEvent.change(screen.getByLabelText(/team token/i), {
      target: { value: "bad" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sync from rctf/i }));

    expect(await screen.findByText("rCTF sync requires a team_token.")).toBeInTheDocument();
  });
});
