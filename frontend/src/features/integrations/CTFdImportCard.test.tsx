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
    });
  }),
  http.get("http://localhost/api/integrations/ctfd/config", () =>
    HttpResponse.json({
      base_url: "",
      configured: false,
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

  it("loads saved base url from config", async () => {
    server.use(
      http.get("http://localhost/api/integrations/ctfd/config", () =>
        HttpResponse.json({
          base_url: "https://saved-ctfd.example.com",
          configured: true,
        }),
      ),
    );

    renderWithProviders(<CTFdImportCard />);

    fireEvent.click(screen.getByRole("button", { name: /load saved base url/i }));

    const baseUrlInput = (await screen.findByLabelText(/base url/i)) as HTMLInputElement;
    expect(baseUrlInput.value).toBe("https://saved-ctfd.example.com");
    expect(screen.getByText("Loaded saved base URL.")).toBeInTheDocument();
  });

  it("supports switching to api token auth mode", async () => {
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
