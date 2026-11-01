import { useQuery } from "@tanstack/react-query";

import { api, enc } from "@/lib/api";
import type { AccessToken, Finding, MemoryItem, MemoryRecord, Provider, Setting } from "@/lib/types";

export const keys = {
  findings: ["findings", "open"] as const,
  memory: (id: string) => ["memory", id] as const,
  providers: ["providers"] as const,
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

export const useSettings = () =>
  useQuery({ queryKey: keys.settings, queryFn: () => api<{ items: Setting[] }>("/settings").then((d) => d.items) });
