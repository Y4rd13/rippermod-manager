import { createBrowserRouter, Navigate } from "react-router";

import { OnboardingLayout } from "@/layouts/OnboardingLayout";
import { RootLayout } from "@/layouts/RootLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { GameDetailPage } from "@/pages/GameDetailPage";
import { GamesPage } from "@/pages/GamesPage";
import { OnboardingPage } from "@/pages/OnboardingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { UpdatesPage } from "@/pages/UpdatesPage";
import { OnboardingGuard } from "@/router/OnboardingGuard";

export const router = createBrowserRouter([
  {
    path: "/onboarding",
    element: <OnboardingLayout />,
    children: [{ index: true, element: <OnboardingPage /> }],
  },
  {
    element: <OnboardingGuard />,
    children: [
      {
        path: "/",
        element: <RootLayout />,
        children: [
          { index: true, element: <Navigate to="/dashboard" replace /> },
          { path: "dashboard", element: <DashboardPage /> },
          { path: "games", element: <GamesPage /> },
          { path: "games/:name", element: <GameDetailPage /> },
          { path: "updates", element: <UpdatesPage /> },
          { path: "settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
]);
