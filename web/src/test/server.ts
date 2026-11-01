// An in-memory stand-in for the REST API the console uses, with the same response shapes.
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import type {
  AccessToken,
  DailyStat,
  Finding,
  MemoryItem,
  MemoryView,
  ModelRole,
  Provider,
  RecallLogEntry,
  MaintenanceRound,
  Overview,
  Setting,
  StartupSettings,
} from "@/lib/types";

export const TOKEN = "good-token";
export const PASSWORD = "admin-password";
const BASE = "http://localhost:3000/api/v1";

interface Db {
  /** Console state: the admin password (null until set) and the current browser's session. */
  password: string | null;
  session: "none" | "bootstrap" | "full";
  memories: MemoryView[];
  findings: Finding[];
  settings: Setting[];
  tokens: AccessToken[];
  providers: Provider[];
  roles: ModelRole[];
  recallLog: RecallLogEntry[];
  dailyStats: DailyStat[];
  startup: StartupSettings;
  rounds: MaintenanceRound[];
  calls: { method: string; path: string; body: unknown }[];
}

export const db: Db = {
  password: PASSWORD,
  session: "full",
  memories: [],
  findings: [],
  settings: [],
  tokens: [],
  providers: [],
  roles: [],
  recallLog: [],
  dailyStats: [],
  startup: defaultStartup(),
  rounds: [],
  calls: [],
};

/** The configuration-file provider: editable as an override, never deletable. */
export const fileProvider = (): Provider => ({
  id: "file",
  name: "openrouter",
  protocol: "openai",
  base_url: "https://openrouter.ai/api/v1",
  source: "file",
  has_key: true,
  api_key_last4: "cret",
  overridden: { base_url: false, api_key: false },
  file_base_url: "https://openrouter.ai/api/v1",
  file_api_key_last4: "cret",
  last_call_at: "2026-11-01T09:00:00+00:00",
  last_call_ok: true,
  last_call_error: null,
  created_at: "2026-10-31T08:00:00+00:00",
  deletable: false,
});

export const initialToken = (): AccessToken => ({
  id: "initial",
  name: "initial",
  source: "file",
  created_at: "2026-10-31T08:00:00+00:00",
  last_used_at: "2026-11-01T09:30:00+00:00",
  revoked_at: null,
});

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
  db.password = PASSWORD;
  db.session = "full";
  db.memories = [];
  db.findings = [];
  db.settings = [];
  db.tokens = [initialToken()];
  db.providers = [fileProvider()];
  db.roles = defaultRoles();
  db.recallLog = [];
  db.dailyStats = [];
  db.startup = defaultStartup();
  db.rounds = [];
  db.calls = [];
}

const ok = (data: unknown) => HttpResponse.json({ ok: true, data });
const fail = (error: string, status: number) => HttpResponse.json({ ok: false, error }, { status });


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
  valid_from: m.valid_from,
});

/** The overview snapshot, built from the same in-memory state the mock serves elsewhere. */
export function overview(): Overview {
  const byDay = new Map<string, { day: string; token: string; writes: number; recalls: number; median_latency_ms: number | null }>();
  for (const stat of db.dailyStats) {
    const entry = byDay.get(stat.day) ?? { day: stat.day, token: "", writes: 0, recalls: 0, median_latency_ms: null };
    entry.writes += stat.writes;
    entry.recalls += stat.recalls;
    if (stat.median_latency_ms !== null) entry.median_latency_ms = stat.median_latency_ms;
    byDay.set(stat.day, entry);
  }
  const last = db.rounds[0] ?? null;
  return {
    findings: [...db.findings.filter((f) => f.status === "open").reduce((acc, f) => acc.set(f.kind, (acc.get(f.kind) ?? 0) + 1), new Map<string, number>())]
      .map(([kind, count]) => ({ kind, count })),
    memories: {
      total: db.memories.filter((m) => m.is_current).length,
      new_7d: db.memories.filter((m) => m.is_current && m.mutation_type === "initial").length,
      evolved_7d: db.memories.filter((m) => m.is_current && m.mutation_type !== "initial").length,
      new_30d: 0,
      evolved_30d: 0,
    },
    last_round: last,
    schedule: "每天 04:17（宿主机 cron，Asia/Shanghai）",
    providers: db.providers.map((p) => ({
      id: p.id,
      name: p.name,
      source: p.source,
      last_call_at: p.last_call_at,
      last_call_ok: p.last_call_ok,
      last_call_error: p.last_call_error,
    })),
    stalest: [...db.memories]
      .filter((m) => m.is_current)
      .sort((a, b) => a.valid_from.localeCompare(b.valid_from))
      .slice(0, 5)
      .map((m) => ({ memory_id: m.memory_id, entity_key: m.entity_key, content: m.content, valid_from: m.valid_from })),
    tokens: db.tokens.map((t) => ({ name: t.name, last_used_at: t.last_used_at, revoked_at: t.revoked_at })),
    daily: [...byDay.values()],
  };
}

/** Startup settings before anything is applied: what the configuration file and defaults give. */
export function defaultStartup(): StartupSettings {
  return {
  effective: {
    port: 8765,
    data_dir: "/app/data",
    vector_backend: "lancedb",
    embedding_model: "openai/text-embedding-3-small",
    embedding_dim: 1536,
    debug: false,
  },
  overrides: {},
  draft: {},
  editable: ["port", "data_dir", "vector_backend", "debug"],
  read_only: {},
  container: false,
    defaults: {},
    last_apply: null,
  };
}

/** The roles as they are before anything is saved: configuration-file provider and llm_model. */
export const defaultRoles = (): ModelRole[] => {
  const defaults = { provider_id: "file", provider_name: "openrouter", model: "deepseek/deepseek-v4.1-flash-1017", timeout: 30 };
  return [
    { role: "write", label: "写入", provider_id: "file", provider_name: "openrouter", model: defaults.model, dimension: null, timeout: 30, custom: false, read_only: false, defaults },
    { role: "maintenance", label: "维护", provider_id: "file", provider_name: "openrouter", model: defaults.model, dimension: null, timeout: 30, custom: false, read_only: false, defaults },
    { role: "embedding", label: "向量", provider_id: "file", provider_name: "openrouter", model: "openai/text-embedding-3-small", dimension: 1536, timeout: 30, custom: false, read_only: true, defaults: null },
  ];
};

async function log(request: Request, path: string) {
  const text = await request.clone().text();
  db.calls.push({ method: request.method, path, body: text ? JSON.parse(text) : undefined });
}

type Params = Record<string, string>;

const guard =
  (fn: (args: { request: Request; params: Params }) => Response | Promise<Response>) =>
  async ({ request, params }: { request: Request; params: Record<string, string | readonly string[] | undefined> }) => {
    // The cookie is HttpOnly and invisible here; the mock keeps one browser's session in db.session.
    if (db.session === "none") return fail("Unauthorized", 401);
    if (db.session === "bootstrap") return fail("Set the admin password first", 403);
    await log(request, new URL(request.url).pathname + new URL(request.url).search);
    return fn({ request, params: params as Params });
  };

export const handlers = [
  http.get(`${BASE}/console/session`, () =>
    ok({ signed_in: db.session !== "none", password_set: db.password !== null, bootstrap: db.session === "bootstrap" })),
  http.post(`${BASE}/console/login`, async ({ request }) => {
    const body = (await request.json()) as { password?: string; token?: string };
    db.calls.push({ method: "POST", path: "/api/v1/console/login", body });
    if (db.password === null) {
      if (body.token !== TOKEN) return fail("令牌无效", 401);
      db.session = "bootstrap";
    } else {
      if (body.password !== db.password) return fail("口令错误", 401);
      db.session = "full";
    }
    return ok({ signed_in: true });
  }),
  http.post(`${BASE}/console/logout`, () => {
    db.session = "none";
    return ok({ signed_in: false });
  }),
  http.put(`${BASE}/console/password`, async ({ request }) => {
    const body = (await request.json()) as { current_password?: string; new_password: string };
    db.calls.push({ method: "PUT", path: "/api/v1/console/password", body });
    if (db.session === "none") return fail("Unauthorized", 401);
    if (!body.new_password) return fail("新口令不能为空", 400);
    if (db.password !== null && body.current_password !== db.password) return fail("当前口令错误", 400);
    db.password = body.new_password;
    db.session = "full";
    return ok({ password_set: true });
  }),
  http.delete(`${BASE}/console/sessions`, () => {
    db.calls.push({ method: "DELETE", path: "/api/v1/console/sessions", body: undefined });
    db.session = "none";
    return ok({ signed_out: 2 });
  }),
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
  http.get(`${BASE}/memories/types`, guard(() => {
    const counts = new Map<string, number>();
    for (const m of db.memories.filter((x) => x.is_current)) counts.set(m.entity_type, (counts.get(m.entity_type) ?? 0) + 1);
    const items = [...counts].sort(([a], [b]) => a.localeCompare(b)).map(([entity_type, count]) => ({ entity_type, count }));
    return ok({ items });
  })),
  http.get(`${BASE}/memories`, guard(({ request }) => {
    const q = new URL(request.url).searchParams;
    const limit = Number(q.get("limit") ?? 100);
    const offset = Number(q.get("offset") ?? 0);
    const type = q.get("entity_type");
    const key = q.get("key")?.toLowerCase();
    const sort = (q.get("sort") ?? "created_at") as keyof MemoryView;
    const dir = q.get("direction") === "asc" ? 1 : -1;
    const rows = db.memories
      .filter((m) => m.is_current && (!type || m.entity_type === type) && (!key || m.entity_key.toLowerCase().includes(key)))
      .sort((a, b) => dir * String(a[sort]).localeCompare(String(b[sort])));
    const results = rows.slice(offset, offset + limit).map(item);
    return ok({ results, total: results.length, matched: rows.length });
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
    const { value } = (await request.json()) as { value: number | boolean };
    if (s.type === "bool" && typeof value !== "boolean") return fail(`${s.key} 只能是 true 或 false`, 400);
    if (s.type !== "bool") {
      const n = Number(value);
      if (s.min !== null && s.max !== null && (n < s.min || n > s.max)) {
        return fail(`${s.key} must be between ${s.min} and ${s.max}`, 400);
      }
    }
    Object.assign(s, { value, source: "console" });
    return ok(s);
  })),
  http.delete(`${BASE}/settings/:key`, guard(({ params }) => {
    const s = db.settings.find((x) => x.key === params.key);
    if (!s) return fail("Unknown setting", 404);
    Object.assign(s, s.file_value !== null ? { value: s.file_value, source: "file" } : { value: s.default, source: "default" });
    return ok(s);
  })),
  http.get(`${BASE}/tokens`, guard(() => ok({ items: db.tokens }))),
  http.post(`${BASE}/tokens`, guard(async ({ request }) => {
    const name = String(((await request.json()) as { name?: string }).name ?? "").trim();
    if (!name) return fail("名称不能为空", 400);
    if (db.tokens.some((t) => t.name === name)) return fail(`名称已被使用：${name}`, 409);
    const token: AccessToken = { id: `t${db.tokens.length}`, name, source: "console", created_at: "2026-11-01T10:00:00+00:00", last_used_at: null, revoked_at: null };
    db.tokens.push(token);
    return HttpResponse.json({ ok: true, data: { ...token, value: `value-of-${name}` } }, { status: 201 });
  })),
  http.delete(`${BASE}/tokens/:id`, guard(({ params }) => {
    const t = db.tokens.find((x) => x.id === params.id);
    if (!t) return fail("Token not found", 404);
    t.revoked_at ??= "2026-11-01T10:05:00+00:00";
    return ok(t);
  })),
  http.get(`${BASE}/providers`, guard(() => ok({ items: db.providers }))),
  http.post(`${BASE}/providers/test`, guard(async ({ request }) => {
    const body = (await request.json()) as { base_url?: string; id?: string };
    if ((body.base_url ?? "").includes("fail")) return ok({ ok: false, models: 0, sample: [], checked: null, reply: null, error: "HTTP 401：invalid api key" });
    return ok({ ok: true, models: 2, sample: ["gpt-4o-mini", "gpt-4.1"], checked: "gpt-4o-mini", reply: "OK" });
  })),
  http.post(`${BASE}/providers`, guard(async ({ request }) => {
    const body = (await request.json()) as { name: string; protocol: string; base_url: string; api_key: string };
    if (!body.name?.trim()) return fail("名称不能为空", 400);
    if (db.providers.some((p) => p.name === body.name)) return fail(`名称已被使用：${body.name}`, 409);
    const created: Provider = {
      id: `p${db.providers.length}`,
      name: body.name,
      protocol: body.protocol as Provider["protocol"],
      base_url: body.base_url,
      source: "console",
      has_key: true,
      api_key_last4: body.api_key.slice(-4),
      overridden: { base_url: false, api_key: false },
      file_base_url: null,
      file_api_key_last4: null,
      last_call_at: null,
      last_call_ok: null,
      last_call_error: null,
      created_at: "2026-11-01T10:00:00+00:00",
      deletable: true,
    };
    db.providers.push(created);
    return HttpResponse.json({ ok: true, data: created }, { status: 201 });
  })),
  http.put(`${BASE}/providers/:id`, guard(async ({ request, params }) => {
    const p = db.providers.find((x) => x.id === params.id);
    if (!p) return fail("Provider not found", 404);
    const body = (await request.json()) as {
      name?: string;
      protocol?: string;
      base_url?: string | null;
      api_key?: string | null;
    };
    if (body.name !== undefined) p.name = body.name;
    if (body.protocol !== undefined) p.protocol = body.protocol as Provider["protocol"];
    if (body.base_url !== undefined) {
      p.base_url = body.base_url ?? (p.file_base_url as string);
      p.overridden.base_url = body.base_url !== null;
    }
    if (body.api_key !== undefined) {
      p.api_key_last4 = body.api_key === null ? p.file_api_key_last4 : body.api_key.slice(-4);
      p.overridden.api_key = body.api_key !== null;
    }
    return ok(p);
  })),
  http.delete(`${BASE}/providers/:id`, guard(({ params }) => {
    const p = db.providers.find((x) => x.id === params.id);
    if (!p) return fail("Provider not found", 404);
    if (!p.deletable) return fail("配置文件 Provider 不能删除，可以恢复为配置文件值", 409);
    if (db.roles.some((r) => r.provider_id === p.id)) return fail("Provider 正被模型用途使用，先改用途再删除", 409);
    db.providers = db.providers.filter((x) => x.id !== params.id);
    return ok({ id: p.id, deleted: true });
  })),
  http.get(`${BASE}/providers/:id/models`, guard(({ params }) => {
    const p = db.providers.find((x) => x.id === params.id);
    if (!p) return fail("Provider not found", 404);
    if (p.base_url.includes("fail")) return fail("HTTP 401：invalid api key", 502);
    return ok({ items: ["gpt-4o-mini", "gpt-4.1"] });
  })),
  http.get("http://localhost:3000/health", () => HttpResponse.json({ status: "ok" })),
  http.get(`${BASE}/overview`, guard(() => ok(overview()))),
  http.get(`${BASE}/overview/rounds`, guard(() => ok({ items: db.rounds }))),
  http.post(`${BASE}/maintenance/run`, guard(() => {
    const round: MaintenanceRound = {
      id: `job-${db.rounds.length + 1}`,
      status: "running",
      started_at: "2026-11-01T10:00:00+00:00",
      finished_at: null,
      duration_ms: null,
      stats: { llm_calls: 0 },
      error: null,
    };
    db.rounds.unshift(round);
    return HttpResponse.json({ ok: true, data: { job_id: round.id } }, { status: 202 });
  })),
  http.get(`${BASE}/startup-settings`, guard(() => ok(db.startup))),
  http.put(`${BASE}/startup-settings`, guard(async ({ request }) => {
    const body = (await request.json()) as Record<string, string | number | boolean>;
    db.startup.draft = { ...db.startup.draft, ...body };
    return ok(db.startup);
  })),
  http.delete(`${BASE}/startup-settings`, guard(() => {
    db.startup.draft = {};
    return ok(db.startup);
  })),
  http.post(`${BASE}/startup-settings/check`, guard(() => {
    const directory = String(db.startup.draft.data_dir ?? "");
    if (directory.includes("bad")) return ok({ ok: false, problems: [`数据目录不存在：${directory}`] });
    return ok({ ok: true, problems: [] });
  })),
  http.post(`${BASE}/startup-settings/apply`, guard(() => {
    if (!Object.keys(db.startup.draft).length) return fail("没有待生效的启动设置", 400);
    db.startup.effective = { ...db.startup.effective, ...db.startup.draft };
    db.startup.overrides = { ...db.startup.overrides, ...db.startup.draft };
    db.startup.last_apply = { status: "applied", at: "2026-11-01T10:00:00+00:00", finished_at: "2026-11-01T10:00:05+00:00" };
    db.startup.draft = {};
    return HttpResponse.json({ ok: true, data: { applying: true } }, { status: 202 });
  })),
  http.get(`${BASE}/recall-log`, guard(({ request }) => {
    const limit = Number(new URL(request.url).searchParams.get("limit") ?? 50);
    const items = [...db.recallLog].sort((a, b) => b.at.localeCompare(a.at)).slice(0, limit);
    return ok({ items, total: db.recallLog.length });
  })),
  http.get(`${BASE}/recall-log/daily`, guard(() => ok({ items: db.dailyStats }))),
  http.delete(`${BASE}/recall-log`, guard(() => {
    const deleted = db.recallLog.length;
    db.recallLog = [];
    return ok({ deleted });
  })),
  http.get(`${BASE}/model-roles`, guard(() => ok({ items: db.roles }))),
  http.post(`${BASE}/model-roles/:role/test`, guard(({ params }) => {
    const role = db.roles.find((r) => r.role === params.role);
    if (!role) return fail("Unknown model role", 404);
    const provider = db.providers.find((p) => p.id === role.provider_id);
    if (provider?.base_url.includes("fail")) return ok({ ok: false, reply: null, error: "HTTP 401：invalid api key" });
    return ok({ ok: true, reply: "OK", error: null });
  })),
  http.put(`${BASE}/model-roles/:role`, guard(async ({ request, params }) => {
    const role = db.roles.find((r) => r.role === params.role);
    if (!role) return fail("Unknown model role", 404);
    if (role.read_only) return fail("向量用途只读：已存的向量是用这个模型算出来的，改了就无法与存量比较", 400);
    const body = (await request.json()) as { provider_id: string; model: string; timeout: number };
    if (!body.model?.trim()) return fail("模型不能为空", 400);
    const provider = db.providers.find((p) => p.id === body.provider_id);
    if (!provider) return fail("Provider not found", 404);
    Object.assign(role, { provider_id: provider.id, provider_name: provider.name, model: body.model, timeout: body.timeout, custom: true });
    return ok(role);
  })),
  http.delete(`${BASE}/model-roles/:role`, guard(({ params }) => {
    const role = db.roles.find((r) => r.role === params.role);
    if (!role) return fail("Unknown model role", 404);
    if (role.read_only) return fail("向量用途只读：已存的向量是用这个模型算出来的，改了就无法与存量比较", 400);
    Object.assign(role, { provider_id: "file", provider_name: "openrouter", model: role.defaults?.model, timeout: 30, custom: false });
    return ok(role);
  })),
];

export const server = setupServer(...handlers);
