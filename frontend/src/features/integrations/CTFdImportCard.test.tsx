import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { CTFdImportCard } from "@/features/integrations/CTFdImportCard";
import { renderWithProviders } from "@/test/render";

let lastSyncPayload: unknown = null;

const server = setupServer(
  http.post("http://localhost/api/integrations/ctfd/sync", async ({ request }) => {
    lastSyncPayload = await request.json();
    return HttpResponse.json({
      synced: 3,
      platform: "ctfd",
      ctf_id: "11111111-1111-1111-1111-111111111111",
      ctf_slug: "ctfd-example-com",
      auth_mode_used: "session_cookie",
      stored_auth_modes: ["session_cookie"],
    });
  }),
  http.get("http://localhost/api/ctfs/11111111-1111-1111-1111-111111111111/integrations/ctfd/config", () =>
    HttpResponse.json({
      base_url: "https://ctfd.example.com",
      configured: true,
      preferred_auth_mode: "session_cookie",
      has_api_token: false,
      has_session_cookie: true,
      stored_auth_modes: ["session_cookie"],
      last_sync_auth_mode: "session_cookie",
      last_submit_auth_mode: null,
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

describe("CTFdImportCard", () => {
  it("syncs challenges with session cookie auth by default", async () => {
    renderWithProviders(<CTFdImportCard />);

    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "https://ctfd.example.com" },
    });
    fireEvent.change(screen.getByLabelText(/session cookie/i), {
      target: { value: "session=abc123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sync from ctfd/i }));

    expect(await screen.findByText("Synced 3 challenges from ctfd.")).toBeInTheDocument();
    expect(await screen.findByText(/Saved CTFd Auth/i)).toBeInTheDocument();
    expect(lastSyncPayload).toEqual({
      base_url: "https://ctfd.example.com",
      auth_mode: "session_cookie",
      session_cookie: "session=abc123",
      api_token: null,
    });
  });

  it("validates required fields", async () => {
    renderWithProviders(<CTFdImportCard />);

    fireEvent.click(screen.getByRole("button", { name: /sync from ctfd/i }));

    expect(await screen.findByText("Base URL is required")).toBeInTheDocument();
    expect(screen.getByText("Session cookie is required")).toBeInTheDocument();
  });

  it("shows backend errors", async () => {
    server.use(
      http.post("http://localhost/api/integrations/ctfd/sync", () =>
        HttpResponse.json(
          {
            detail: "CTFd integration is not configured. Provide base_url and api_token.",
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(<CTFdImportCard />);

    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "https://ctfd.example.com" },
    });
    fireEvent.change(screen.getByLabelText(/session cookie/i), {
      target: { value: "session=bad-cookie" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sync from ctfd/i }));

    expect(await screen.findByText("CTFd integration is not configured. Provide base_url and api_token.")).toBeInTheDocument();
  });

  it("supports switching to api token auth mode", async () => {
    server.use(
      http.post("http://localhost/api/integrations/ctfd/sync", async ({ request }) => {
        lastSyncPayload = await request.json();
        return HttpResponse.json({
          synced: 3,
          platform: "ctfd",
          ctf_id: "11111111-1111-1111-1111-111111111111",
          ctf_slug: "ctfd-example-com",
          auth_mode_used: "api_token",
          stored_auth_modes: ["api_token"],
        });
      }),
      http.get("http://localhost/api/ctfs/11111111-1111-1111-1111-111111111111/integrations/ctfd/config", () =>
        HttpResponse.json({
          base_url: "https://ctfd.example.com",
          configured: true,
          preferred_auth_mode: "api_token",
          has_api_token: true,
          has_session_cookie: false,
          stored_auth_modes: ["api_token"],
          last_sync_auth_mode: "api_token",
          last_submit_auth_mode: null,
          last_submit_status: null,
          updated_at: "2026-02-26T00:00:00Z",
        }),
      ),
    );

    renderWithProviders(<CTFdImportCard />);

    fireEvent.change(screen.getByLabelText(/auth mode/i), {
      target: { value: "api_token" },
    });
    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "https://ctfd.example.com" },
    });
    fireEvent.change(screen.getByLabelText(/api token/i), {
      target: { value: "token-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sync from ctfd/i }));

    expect(await screen.findByText("Synced 3 challenges from ctfd.")).toBeInTheDocument();
    expect(lastSyncPayload).toEqual({
      base_url: "https://ctfd.example.com",
      auth_mode: "api_token",
      api_token: "token-123",
      session_cookie: null,
    });
  });
});
