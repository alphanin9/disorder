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
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ChallengesPage", () => {
  it("renders challenges from API", async () => {
    renderWithProviders(<ChallengesPage />);

    expect(await screen.findByText("Warmup")).toBeInTheDocument();
    expect(screen.getByText("misc")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });
});
