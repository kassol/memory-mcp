// Console session state. The cookie itself is invisible to scripts; the page asks the service.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";

import { consoleApi, setUnauthorizedHandler } from "@/lib/api";

export interface SessionStatus {
  signed_in: boolean;
  password_set: boolean;
  bootstrap: boolean;
}

interface Session {
  status: SessionStatus | undefined;
  /** Sign in with the admin password, or with the access token while no password exists. */
  signIn: (credential: { password: string } | { token: string }) => Promise<void>;
  setPassword: (newPassword: string, currentPassword?: string) => Promise<void>;
  signOut: () => Promise<void>;
  signOutEverywhere: () => Promise<void>;
}

const SessionContext = createContext<Session | null>(null);
const KEY = ["console-session"] as const;

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: KEY, queryFn: () => consoleApi<SessionStatus>("/console/session"), staleTime: Infinity });

  // Data is dropped whenever the session changes, so nothing from one session shows in the next.
  const refresh = useCallback(async () => {
    const next = await consoleApi<SessionStatus>("/console/session");
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== KEY[0] });
    queryClient.setQueryData(KEY, next);
  }, [queryClient]);

  useEffect(() => setUnauthorizedHandler(() => void refresh()), [refresh]);

  const value = useMemo<Session>(() => ({
    status: status.data,
    signIn: async (credential) => {
      await consoleApi("/console/login", { method: "POST", body: credential });
      await refresh();
    },
    setPassword: async (newPassword, currentPassword) => {
      await consoleApi("/console/password", { method: "PUT", body: { new_password: newPassword, current_password: currentPassword } });
      await refresh();
    },
    signOut: async () => {
      await consoleApi("/console/logout", { method: "POST" });
      await refresh();
    },
    signOutEverywhere: async () => {
      await consoleApi("/console/sessions", { method: "DELETE" });
      await refresh();
    },
  }), [status.data, refresh]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionProvider");
  return session;
}
