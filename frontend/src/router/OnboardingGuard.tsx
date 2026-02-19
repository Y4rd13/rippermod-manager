import { Navigate, Outlet } from "react-router";

import { useOnboardingStatus } from "@/hooks/queries";

export function OnboardingGuard() {
  const { data, isLoading } = useOnboardingStatus();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin h-8 w-8 border-2 border-accent border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!data?.completed) {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}
