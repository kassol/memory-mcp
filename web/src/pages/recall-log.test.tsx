import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, memory, reset, setting } from "@/test/server";

beforeEach(() => {
  reset();
  db.settings.push(
    setting({ key: "recall_log_enabled", label: "记录检索", group: "behaviour", type: "bool", default: true, value: true, min: null, max: null, recommended: null, note: null }),
  );
  db.memories.push(
    memory({ entity_key: "fact:editor", content: "Prefers Zed" }),
    memory({ entity_key: "fact:host", content: "Deploys from laptop" }),
  );
  db.recallLog.push(
    {
      id: "r1",
      at: "2026-11-01T09:30:00+00:00",
      token: "initial",
      query: "editor",
      latency_ms: 42.5,
      results: 2,
      memory_ids: ["m2", "m1"],
    },
    {
      id: "r2",
      at: "2026-11-01T08:00:00+00:00",
      token: null,
      query: "deploy",
      latency_ms: 8,
      results: 0,
      memory_ids: [],
    },
  );
});

async function openLog() {
  const view = await renderAt("/records");
  await view.user.click(await screen.findByRole("button", { name: "检索记录" }));
  return view;
}

const row = async (query: string) => (await screen.findByText(query)).closest("tr") as HTMLElement;

test("log entries show the query, token, latency and result count", async () => {
  await openLog();
  const first = await row("editor");
  expect(within(first).getByText("initial")).toBeInTheDocument();
  expect(within(first).getByText("42.5 ms")).toBeInTheDocument();
  expect(within(first).getByRole("button", { name: "打开第 2 条结果" })).toBeInTheDocument();
  expect(within(first).getByText("2026-11-01 17:30")).toBeInTheDocument();
  // A console session has no access token.
  expect(within(await row("deploy")).getByText("面板")).toBeInTheDocument();
  expect(screen.getByText(/共 2 条，显示最近 2 条/)).toBeInTheDocument();
});

test("a result opens the memory in the sheet", async () => {
  const { user } = await openLog();
  const entry = await row("editor");
  await user.click(within(entry).getByRole("button", { name: "打开第 1 条结果" }));
  expect(await screen.findByText("记忆详情")).toBeInTheDocument();
  expect((await screen.findAllByText("Deploys from laptop")).length).toBeGreaterThan(0);
});

test("clearing asks first, then empties the log", async () => {
  const { user } = await openLog();
  await row("editor");
  await user.click(screen.getByRole("button", { name: "清空记录" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(within(dialog).getByText(/日统计/)).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "清空" }));
  expect(await screen.findByText("还没有检索记录")).toBeInTheDocument();
  expect(db.calls.find((c) => c.method === "DELETE")?.path).toBe("/api/v1/recall-log");
});

test("the logging switch saves the setting", async () => {
  const { user } = await openLog();
  const toggle = await screen.findByRole("switch", { name: "记录检索" });
  expect(toggle).toHaveAttribute("aria-checked", "true");
  await user.click(toggle);
  await waitFor(() =>
    expect(db.calls.find((c) => c.method === "PUT" && c.path === "/api/v1/settings/recall_log_enabled")).toMatchObject({
      body: { value: false },
    }),
  );
  expect(await screen.findByText(/记录检索（关闭）/)).toBeInTheDocument();
});
