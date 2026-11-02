import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, reset, setting } from "@/test/server";

beforeEach(() => {
  reset();
});

test("the schedule is shown read-only and an empty history says so", async () => {
  await renderAt("/maintenance");
  expect(await screen.findByText("维护检查")).toBeInTheDocument();
  expect(await screen.findByText(/每天 04:17/)).toBeInTheDocument();
  expect(screen.getByText("还没有运行过维护")).toBeInTheDocument();
});

test("starting a round posts it and the new round appears as running", async () => {
  const { user } = await renderAt("/maintenance");
  await user.click(await screen.findByRole("button", { name: "立即运行一轮" }));
  await waitFor(() => expect(db.calls.find((c) => c.path === "/api/v1/maintenance/run")?.method).toBe("POST"));
  expect(await screen.findByText("运行中")).toBeInTheDocument();
  expect(db.rounds).toHaveLength(1);
});

test("past rounds show duration, model calls, findings and errors", async () => {
  db.rounds.push(
    {
      id: "job-2",
      status: "done",
      started_at: "2026-11-01T03:17:00+00:00",
      finished_at: "2026-11-01T03:18:30+00:00",
      duration_ms: 90_000,
      stats: { llm_calls: 12, duplicate: 2, internal_contradiction: 1 },
      error: null,
    },
    {
      id: "job-1",
      status: "failed",
      started_at: "2026-10-31T03:17:00+00:00",
      finished_at: "2026-10-31T03:17:05+00:00",
      duration_ms: 5_000,
      stats: {},
      error: "LLM request failed",
    },
  );
  await renderAt("/maintenance");
  const done = (await screen.findByText("完成")).closest("tr") as HTMLElement;
  expect(within(done).getByText("90.0 s")).toBeInTheDocument();
  expect(within(done).getByText("12")).toBeInTheDocument();
  expect(within(done).getByText("3")).toBeInTheDocument();

  const failed = screen.getByText("失败").closest("tr") as HTMLElement;
  expect(within(failed).getByText("LLM request failed")).toBeInTheDocument();
  // Refresh re-reads the history.
  await waitFor(() => expect(screen.getByRole("button", { name: "刷新维护" })).toBeInTheDocument());
});

test("the run panel names the per-round model budget", async () => {
  db.settings.push(
    setting({ key: "maintenance_max_llm_calls", label: "维护单轮模型调用上限", group: "behaviour", type: "int", default: 100, value: 100, min: 0, max: 1000 }),
  );
  await renderAt("/maintenance");
  expect(await screen.findByText(/单轮最多 100 次模型调用/)).toBeInTheDocument();
});
