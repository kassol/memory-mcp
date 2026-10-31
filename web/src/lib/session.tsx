// Sign-in state for the access token (until the admin password ticket replaces it).
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, clearToken, getToken, setToken, setUnauthorizedHandler } from "@/lib/api";

interface Session {
  signedIn: boolean;
  message: string;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [signedIn, setSignedIn] = useState(() => !!getToken());
  const [message, setMessage] = useState("");

  const signOut = useCallback(() => {
    clearToken();
    queryClient.clear();
    setSignedIn(false);
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      queryClient.clear();
      setMessage("令牌无效，请重新输入。");
      setSignedIn(false);
    });
  }, [queryClient]);

  const signIn = useCallback(async (token: string) => {
    setToken(token);
    setMessage("");
    await api("/findings?status=open");
    setSignedIn(true);
  }, []);

  const value = useMemo(() => ({ signedIn, message, signIn, signOut }), [signedIn, message, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionProvider");
  return session;
}
