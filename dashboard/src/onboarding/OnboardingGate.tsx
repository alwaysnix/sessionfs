import { Navigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import { getItem } from '../utils/storage';
import { onboardingDismissedKey } from './GettingStartedPage';

/**
 * Wraps the root "/" route. Redirects first-time users (0 sessions, 0 projects,
 * onboarding not dismissed) to /getting-started. Everyone else passes through.
 */
export default function OnboardingGate({ children }: { children: React.ReactNode }) {
  const { auth } = useAuth();

  // If onboarding was dismissed (scoped to this user + server), skip all checks
  const dismissed = getItem(onboardingDismissedKey(auth?.baseUrl, auth?.apiKey)) === '1';

  const sessions = useQuery({
    queryKey: ['sessions', { page: 1, page_size: 1 }],
    queryFn: () => auth!.client.listSessions({ page: 1, page_size: 1 }),
    enabled: !!auth && !dismissed,
    staleTime: 30_000,
  });

  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: () => auth!.client.listProjects(),
    enabled: !!auth && !dismissed,
    staleTime: 30_000,
  });

  // If dismissed, render children immediately
  if (dismissed) return <>{children}</>;

  // Wait for both queries to resolve before deciding
  if (sessions.isLoading || projects.isLoading) return null;

  // If either query errored, don't redirect — show the normal page
  // (or its error state). Transient API failures must never misroute
  // existing users into onboarding.
  if (sessions.isError || projects.isError) return <>{children}</>;

  const hasSession = (sessions.data?.total ?? 0) > 0;
  const hasProject = (projects.data?.length ?? 0) > 0;

  if (!hasSession && !hasProject) {
    return <Navigate to="/getting-started" replace />;
  }

  return <>{children}</>;
}
