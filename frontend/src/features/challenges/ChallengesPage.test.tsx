import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { screen } from "@testing-library/react";

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
  it("renders challenges from API", async () => {
    renderWithProviders(<ChallengesPage />);

    expect(await screen.findByText("Warmup")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Disorder CTF" })).toBeInTheDocument();
    expect(screen.getByText("misc")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });
});
