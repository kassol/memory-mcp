// An in-memory stand-in for the REST API the console uses, with the same response shapes.
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import type { Finding, MemoryItem, MemoryView, Setting } from "@/lib/types";

export const TOKEN = "good-token";
const BASE = "http://localhost:3000/api/v1";

interface Db {
  memories: MemoryView[];
  findings: Finding[];
  settings: Setting[];
  calls: { method: string; path: string; body: unknown }[];
}

export const db: Db = { memories: [], findings: [], settings: [], calls: [] };

let seq = 0;
export function memory(over: Partial<MemoryView> & { entity_key: string; content: string }): MemoryView {
  seq += 1;
  return {
    memory_id: `m${seq}`,
    entity_type: over.entity_key.split(":")[0],
    mutation_type: "initial",
    created_at: `2026-10-${String(seq).padStart(2, "0")}T08:00:00+00:00`,
    valid_from: `2026-10-${String(seq).padStart(2, "0")}T08:00:00+00:00`,
    is_current: true,
    conflict: false,
    archived_reason: null,
    ...over,
  };
}

export function setting(over: Partial<Setting> & { key: string }): Setting {
  return {
    label: over.key,
    group: "advanced",
    type: "float",
    description: "说明",
    default: 2,
    min: 0,
    max: 10,
    recommended: 2,
    note: "评估依据",
    value: 2,
    source: "default",
    file_value: null,
    ...over,
  };
}

export function reset() {
  seq = 0;
  db.memories = [];
  db.findings = [];
  db.settings = [];
  db.calls = [];
}

const ok = (data: unknown) => HttpResponse.json({ ok: true, data });
const fail = (error: string, status: number) => HttpResponse.json({ ok: false, error }, { status });

function authorized(request: Request) {
  return request.headers.get("Authorization") === `Bearer ${TOKEN}`;
}

const record = (m: MemoryView) => ({
  ...m,
  versions: db.memories.filter((v) => v.entity_key === m.entity_key).reverse(),
});

const item = (m: MemoryView): MemoryItem => ({
  memory_id: m.memory_id,
  entity_key: m.entity_key,
  entity_type: m.entity_type,
  content: m.content,
  created_at: m.created_at,
});

async function log(request: Request, path: string) {
  const text = await request.clone().text();
  db.calls.push({ method: request.method, path, body: text ? JSON.parse(text) : undefined });
}

type Params = Record<string, string>;

const guard =
  (fn: (args: { request: Request; params: Params }) => Response | Promise<Response>) =>
  async ({ request, params }: { request: Request; params: Record<string, string | readonly string[] | undefined> }) => {
    if (!request.headers.get("Authorization")) return fail("Unauthorized", 401);
    if (!authorized(request)) return fail("Forbidden", 403);
    await log(request, new URL(request.url).pathname + new URL(request.url).search);
    return fn({ request, params: params as Params });
  };

export const handlers = [
  http.get(`${BASE}/findings`, guard(() => {
    const items = db.findings.filter((f) => f.status === "open");
    return ok({ items, total: items.length });
  })),
  http.post(`${BASE}/findings/:id/dismiss`, guard(({ params }) => {
    const f = db.findings.find((x) => x.id === params.id);
    if (!f) return fail("Finding not found", 404);
    f.status = "dismissed";
    return ok({ id: f.id, status: "dismissed" });
  })),
  http.get(`${BASE}/memories/search`, guard(({ request }) => {
    const query = new URL(request.url).searchParams.get("query") ?? "";
    const results = db.memories.filter((m) => m.is_current && m.content.includes(query)).map(item);
    return ok({ results, total: results.length });
  })),
  http.get(`${BASE}/memories`, guard(({ request }) => {
    const q = new URL(request.url).searchParams;
    const limit = Number(q.get("limit") ?? 100);
    const offset = Number(q.get("offset") ?? 0);
    const type = q.get("entity_type");
    let rows = db.memories.filter((m) => m.is_current && (!type || m.entity_type === type));
    rows = q.get("order") === "valid_from"
      ? [...rows].sort((a, b) => a.valid_from.localeCompare(b.valid_from))
      : [...rows].sort((a, b) => b.created_at.localeCompare(a.created_at));
    const results = rows.slice(offset, offset + limit).map(item);
    return ok({ results, total: results.length });
  })),
  http.get(`${BASE}/memories/:id`, guard(({ params }) => {
    const m = db.memories.find((x) => x.memory_id === params.id);
    return m ? ok(record(m)) : fail("Memory not found", 404);
  })),
  http.post(`${BASE}/memories/:id/correct`, guard(async ({ request, params }) => {
    const m = db.memories.find((x) => x.memory_id === params.id);
    if (!m) return fail("Memory not found", 404);
    const { content } = (await request.json()) as { content: string };
    m.is_current = false;
    const next = memory({ entity_key: m.entity_key, content: content.trim(), mutation_type: "correction" });
    db.memories.push(next);
    return ok(next);
  })),
  http.post(`${BASE}/memories/:id/archive`, guard(async ({ request, params }) => {
    const m = db.memories.find((x) => x.memory_id === params.id);
    if (!m) return fail("Memory not found", 404);
    const { reason } = (await request.json()) as { reason: string };
    m.is_current = false;
    m.archived_reason = reason;
    return ok({ status: "archived" });
  })),
  http.get(`${BASE}/settings`, guard(() => ok({ items: db.settings }))),
  http.put(`${BASE}/settings/:key`, guard(async ({ request, params }) => {
    const s = db.settings.find((x) => x.key === params.key);
    if (!s) return fail("Unknown setting", 404);
    const { value } = (await request.json()) as { value: number };
    if (value < s.min || value > s.max) return fail(`${s.key} must be between ${s.min} and ${s.max}`, 400);
    Object.assign(s, { value, source: "console" });
    return ok(s);
  })),
  http.delete(`${BASE}/settings/:key`, guard(({ params }) => {
    const s = db.settings.find((x) => x.key === params.key);
    if (!s) return fail("Unknown setting", 404);
    Object.assign(s, s.file_value !== null ? { value: s.file_value, source: "file" } : { value: s.default, source: "default" });
    return ok(s);
  })),
];

export const server = setupServer(...handlers);
