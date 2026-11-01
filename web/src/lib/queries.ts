import { useQuery } from "@tanstack/react-query";

import { api, enc } from "@/lib/api";
import type {
  AccessToken,
  DailyStat,
  Finding,
  MemoryItem,
  MemoryRecord,
  ModelRole,
  Provider,
  RecallLogEntry,
  Setting,
  StartupSettings,
} from "@/lib/types";

export const keys = {
  findings: ["findings", "open"] as const,
  memory: (id: string) => ["memory", id] as const,
  models: (providerId: string) => ["models", providerId] as const,
  providers: ["providers"] as const,
  overview: ["overview"] as const,
  recallLog: (limit: number) => ["recall-log", limit] as const,
  rounds: ["maintenance-rounds"] as const,
  roles: ["model-roles"] as const,
  startup: ["startup-settings"] as const,
  records: ["records"] as const,
  search: (query: string, type: string) => ["search", query, type] as const,
  settings: ["settings"] as const,
  tokens: ["tokens"] as const,
};

export const useFindings = () =>
  useQuery({
    queryKey: keys.findings,
    queryFn: () => api<{ items: Finding[]; total: number }>("/findings?status=open"),
  });

export const useMemory = (id: string | null) =>
  useQuery({
    queryKey: keys.memory(id ?? ""),
    queryFn: () => api<MemoryRecord>(`/memories/${enc(id!)}`),
    enabled: !!id,
  });

export const searchMemories = (query: string, type: string, limit: number) => {
  const q = new URLSearchParams({ query, limit: String(limit) });
  if (type) q.set("entity_type", type);
  return api<{ results: MemoryItem[] }>(`/memories/search?${q}`).then((d) => d.results);
};

export const useTokens = () =>
  useQuery({ queryKey: keys.tokens, queryFn: () => api<{ items: AccessToken[] }>("/tokens").then((d) => d.items) });

export const useProviders = () =>
  useQuery({
    queryKey: keys.providers,
    queryFn: () => api<{ items: Provider[] }>("/providers").then((d) => d.items),
  });

export const useModelRoles = () =>
  useQuery({
    queryKey: keys.roles,
    queryFn: () => api<{ items: ModelRole[] }>("/model-roles").then((d) => d.items),
  });

/** The model list of one provider, for the role pickers. A provider can be unreachable, so no retries. */
export const useModels = (providerId: string) =>
  useQuery({
    queryKey: keys.models(providerId),
    queryFn: () => api<{ items: string[] }>(`/providers/${enc(providerId)}/models`).then((d) => d.items),
    enabled: !!providerId,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

export const useRecallLog = (limit: number) =>
  useQuery({
    queryKey: keys.recallLog(limit),
    queryFn: () => api<{ items: RecallLogEntry[]; total: number }>(`/recall-log?limit=${limit}`),
  });

export const useDailyStats = (days = 30) =>
  useQuery({
    queryKey: ["daily-stats", days],
    queryFn: () => api<{ items: DailyStat[] }>(`/recall-log/daily?days=${days}`).then((d) => d.items),
  });

export const useStartupSettings = () =>
  useQuery({ queryKey: keys.startup, queryFn: () => api<StartupSettings>("/startup-settings"), retry: false });

export const useSettings = () =>
  useQuery({ queryKey: keys.settings, queryFn: () => api<{ items: Setting[] }>("/settings").then((d) => d.items) });
