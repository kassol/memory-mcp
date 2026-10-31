import { screen, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, memory, reset } from "@/test/server";

const rows = () => within(screen.getByRole("listbox")).getAllByRole("option");

beforeEach(reset);

function seed(n: number) {
  for (let i = 0; i < n; i++) {
    db.memories.push(memory({ entity_key: `fact:n${i}`, content: `note ${i}`, entity_type: i % 2 ? "fact" : "tool" }));
  }
}

test("records load 50 at a time, newest first, and load more appends", async () => {
  seed(60);
  const { user } = await renderAt("/records");
  expect(await screen.findByText("已载入 50 条")).toBeInTheDocument();
  expect(rows()[0]).toHaveTextContent("note 59");
  await user.click(screen.getByRole("button", { name: "载入更多" }));
  expect(await screen.findByText("已载入 60 条")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "载入更多" })).not.toBeInTheDocument();
  expect(db.calls.map((c) => c.path)).toContain("/api/v1/memories?limit=50&offset=50&order=created_at");
});

test("stale-first order and the type filter go to the server", async () => {
  seed(4);
  const { user } = await renderAt("/records");
  await screen.findByText("已载入 4 条");
  await user.selectOptions(screen.getByRole("combobox", { name: "排序" }), "valid_from");
  expect(await screen.findByText("note 0")).toBeInTheDocument();
  expect(rows()[0]).toHaveTextContent("note 0");
  await user.type(screen.getByRole("textbox", { name: "按类型过滤" }), "fact{Enter}");
  expect(await screen.findByText("已载入 2 条")).toBeInTheDocument();
  expect(db.calls.map((c) => c.path)).toContain("/api/v1/memories?limit=50&offset=0&order=valid_from&entity_type=fact");
});

test("search lists the best matches; Escape returns to the list", async () => {
  seed(3);
  db.memories.push(memory({ entity_key: "fact:gpu", content: "RTX 3090 runs Qwen3.6-35B" }));
  const { user } = await renderAt("/records");
  await screen.findByText("已载入 4 条");
  const box = screen.getByRole("searchbox", { name: "检索" });
  await user.type(box, "Qwen3.6{Enter}");
  expect(await screen.findByText("最相关的 1 条")).toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "排序" })).not.toBeInTheDocument();
  await user.type(box, "{Escape}");
  expect(await screen.findByText("已载入 4 条")).toBeInTheDocument();

  await user.type(box, "nothing like this{Enter}");
  expect(await screen.findByText("没有匹配的记忆")).toBeInTheDocument();
});

test("opening a record shows its full text and version history; correcting adds a version", async () => {
  const old = memory({ entity_key: "fact:city", content: "Lives in Shanghai", is_current: false });
  const cur = memory({ entity_key: "fact:city", content: "Lives in Suzhou", mutation_type: "evolution", conflict: true });
  db.memories.push(old, cur);
  const { user, router } = await renderAt("/records");
  await user.click(await screen.findByRole("option", { name: /Lives in Suzhou/ }));
  expect(router.state.location.search).toEqual({ memory: cur.memory_id });
  expect(await screen.findByRole("heading", { name: "版本历史（2）" })).toBeInTheDocument();
  expect(screen.getByText("冲突合并", { selector: "section[aria-label] span" })).toBeInTheDocument();

  const card = screen.getByRole("region", { name: "fact:city" });
  await user.click(within(card).getByRole("button", { name: "改正" }));
  const area = within(card).getByRole("textbox", { name: "改正后的完整内容" });
  await user.clear(area);
  await user.type(area, "Lives in Hangzhou");
  await user.click(within(card).getByRole("button", { name: "保存为新版本" }));
  expect(await screen.findByRole("heading", { name: "版本历史（3）" })).toBeInTheDocument();
  expect(router.state.location.search).not.toEqual({ memory: cur.memory_id });
});

test("archiving a record drops it from the list", async () => {
  db.memories.push(memory({ entity_key: "fact:a", content: "keep me" }), memory({ entity_key: "fact:b", content: "drop me" }));
  const { user } = await renderAt("/records");
  await user.click(await screen.findByRole("option", { name: /drop me/ }));
  const card = await screen.findByRole("region", { name: "fact:b" });
  await user.click(within(card).getByRole("button", { name: "归档" }));
  await user.type(within(card).getByRole("textbox", { name: "归档原因" }), "obsolete");
  await user.click(within(card).getByRole("button", { name: "确认归档" }));
  expect(await screen.findByText("已载入 1 条")).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /drop me/ })).not.toBeInTheDocument();
  expect(screen.getByText("选一条记忆")).toBeInTheDocument();
});

test("a memory linked from the command palette opens directly", async () => {
  const m = memory({ entity_key: "fact:linked", content: "opened by link" });
  db.memories.push(m);
  await renderAt(`/records?memory=${m.memory_id}`);
  expect(await screen.findByRole("region", { name: "fact:linked" })).toBeInTheDocument();
});
