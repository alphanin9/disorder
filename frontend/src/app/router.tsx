import { createBrowserRouter } from "react-router-dom";

import { AppLayout } from "@/features/layout/AppLayout";
import { ChallengeDetailPage } from "@/features/challenges/ChallengeDetailPage";
import { ChallengesPage } from "@/features/challenges/ChallengesPage";
import { RunPage } from "@/features/runs/RunPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <ChallengesPage />,
      },
      {
        path: "challenges/:challengeId",
        element: <ChallengeDetailPage />,
      },
      {
        path: "runs/:runId",
        element: <RunPage />,
      },
    ],
  },
]);
