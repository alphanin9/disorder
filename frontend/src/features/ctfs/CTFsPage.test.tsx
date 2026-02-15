import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { screen } from "@testing-library/react";

import { CTFsPage } from "@/features/ctfs/CTFsPage";
import { renderWithProviders } from "@/test/render";

const server = setupServer(
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
  http.get("http://localhost/api/auth/codex/status", () =>
    HttpResponse.json({
      configured: false,
      active_tag: null,
      tags: [],
    }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("CTFsPage", () => {
  it("renders ctf rows", async () => {
    renderWithProviders(<CTFsPage />, ["/ctfs"]);

    expect(await screen.findByText("Disorder CTF")).toBeInTheDocument();
    expect(screen.getByText(/default flag regex:/i)).toBeInTheDocument();
  });
});
