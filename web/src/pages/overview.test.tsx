import { screen, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, memory, reset } from "@/test/server";

beforeEach(() => {
  reset();
  db.memories.push(
    memory({ entity_key: "fact:old-editor", content: "Prefers Vim", created_at: "2026-01-01T08:00:00+00:00", valid_from: "2026-01-01T08:00:00+00:00" }),
    memory({ entity_key: "fact:host", content: "Deploys from laptop", mutation_type: "update" }),
  );
  db.findings.push(
    { id: "f1", kind: "duplicate", memory_id: "m1", other_memory_id: "m2", entity_key: "fact:a", detail: null, status: "open", created_at: "2026-11-01T08:00:00+00:00" },
    { id: "f2", kind: "duplicate", memory_id: "m1", other_memory_id: "m2", entity_key: "fact:b", detail: null, status: "open", created_at: "2026-11-01T08:00:00+00:00" },
    { id: "f3", kind: "internal_contradiction", memory_id: "m1", other_memory_id: null, entity_key: "fact:c", detail: null, status: "open", created_at: "2026-11-01T08:00:00+00:00" },
  );
  db.rounds.push({
    id: "job-1",
    status: "done",
    started_at: "2026-11-01T03:17:00+00:00",
    finished_at: "2026-11-01T03:18:30+00:00",
    duration_ms: 90_000,
    stats: { llm_calls: 12, duplicate: 2, internal_contradiction: 1 },
    error: null,
  });
  db.dailyStats.push(
    { day: "2026-10-31", token: "initial", writes: 4, recalls: 6, median_latency_ms: 40 },
    { day: "2026-11-01", token: "initial", writes: 2, recalls: 3, median_latency_ms: 35 },
  );
  db.providers[0].last_call_ok = false;
  db.providers[0].last_call_error = "对话：HTTP 401";
  db.providers[0].last_call_at = "2026-11-01T09:00:00+00:00";
});

test("findings, memory movement and the last round are on one screen", async () => {
  await renderAt("/overview");
  expect(await screen.findByText("待审发现")).toBeInTheDocument();
  expect(screen.getByText("重复")).toBeInTheDocument();
  expect(screen.getByText("内部矛盾")).toBeInTheDocument();
  const go = screen.getByRole("link", { name: "去处理" });
  expect(go.getAttribute("href")).toContain("/docket");

  expect(screen.getByText("当前记忆")).toBeInTheDocument();
  expect(screen.getByText("完成")).toBeInTheDocument();
  expect(screen.getByText(/模型调用 12 次，发现 3/)).toBeInTheDocument();
  expect(db.rounds).toHaveLength(1);
});

test("chatty providers, stalest memories and token use are listed", async () => {
  await renderAt("/overview");
  expect(await screen.findByText("openrouter")).toBeInTheDocument();
  expect(screen.getByText("失败")).toBeInTheDocument();
  expect(screen.getByText("对话：HTTP 401")).toBeInTheDocument();

  const stalest = screen.getByText("最久未更新的记忆").closest("[data-slot=card]") as HTMLElement;
  const first = within(stalest).getAllByRole("link")[0];
  expect(within(first).getByText("Prefers Vim")).toBeInTheDocument();
  expect(first.getAttribute("href")).toContain("memory=m1");

  expect(within(await screen.findByText("访问令牌").then((el) => Promise.resolve(el.closest("[data-slot=card]") as HTMLElement))).getByText("initial")).toBeInTheDocument();
});

test("the 30-day charts render for writes, recalls and latency", async () => {
  await renderAt("/overview");
  expect(await screen.findByText("每日写入")).toBeInTheDocument();
  expect(screen.getByText("每日召回")).toBeInTheDocument();
  expect(screen.getByText("召回耗时中位数")).toBeInTheDocument();
  // ChartContainer marks each chart, so three charts means three of them rendered.
  expect(document.querySelectorAll("[data-chart]")).toHaveLength(3);
});
