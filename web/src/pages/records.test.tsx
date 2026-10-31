import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, memory, reset } from "@/test/server";

beforeEach(reset);

const bodyRows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);
const listCalls = () => db.calls.filter((c) => c.path.startsWith("/api/v1/memories?")).map((c) => c.path);

function seed(n: number) {
  for (let i = 0; i < n; i++) {
    db.memories.push(memory({ entity_key: `fact:n${String(i).padStart(2, "0")}`, content: `note ${i}`, entity_type: i % 2 ? "fact" : "tool" }));
  }
}

test("records show as a table, 50 per page, newest first, with page controls", async () => {
  seed(60);
  const { user } = await renderAt("/records");
  expect(await screen.findByText("第 1 / 2 页")).toBeInTheDocument();
  expect(screen.getByText("共 60 条")).toBeInTheDocument();
  expect(bodyRows()).toHaveLength(50);
  expect(bodyRows()[0]).toHaveTextContent("note 59");
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "下一页" }));
  expect(await screen.findByText("第 2 / 2 页")).toBeInTheDocument();
  expect(bodyRows()).toHaveLength(10);
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  expect(listCalls()).toContain("/api/v1/memories?limit=50&offset=50&sort=created_at&direction=desc");
});

test("clicking a column header sorts by it on the server, and again reverses it", async () => {
  seed(4);
  const { user } = await renderAt("/records");
  await screen.findByText("共 4 条");
  await user.click(screen.getByRole("button", { name: "Key" }));
  await waitFor(() => expect(bodyRows()[0]).toHaveTextContent("fact:n00"));
  expect(screen.getByRole("columnheader", { name: "Key" })).toHaveAttribute("aria-sort", "ascending");
  await user.click(screen.getByRole("button", { name: "Key" }));
  await waitFor(() => expect(bodyRows()[0]).toHaveTextContent("fact:n03"));
  await user.click(screen.getByRole("button", { name: "生效时间" }));
  await waitFor(() => expect(bodyRows()[0]).toHaveTextContent("fact:n00"));
  expect(listCalls()).toEqual(expect.arrayContaining([
    "/api/v1/memories?limit=50&offset=0&sort=entity_key&direction=asc",
    "/api/v1/memories?limit=50&offset=0&sort=entity_key&direction=desc",
    "/api/v1/memories?limit=50&offset=0&sort=valid_from&direction=asc",
  ]));
});

test("filtering by key and by type goes to the server", async () => {
  seed(4);
  const { user } = await renderAt("/records");
  await screen.findByText("共 4 条");
  await user.type(screen.getByRole("textbox", { name: "按 key 过滤" }), "n01{Enter}");
  expect(await screen.findByText("共 1 条")).toBeInTheDocument();
  await user.clear(screen.getByRole("textbox", { name: "按 key 过滤" }));
  await user.keyboard("{Enter}");
  await screen.findByText("共 4 条");

  await user.click(screen.getByRole("combobox", { name: "按类型过滤" }));
  await user.click(await screen.findByRole("option", { name: "fact（2）" }));
  expect(await screen.findByText("共 2 条")).toBeInTheDocument();
  expect(listCalls()).toContain("/api/v1/memories?limit=50&offset=0&sort=created_at&direction=desc&entity_type=fact");
});

test("search lists the best matches; Escape returns to the table", async () => {
  seed(3);
  db.memories.push(memory({ entity_key: "fact:gpu", content: "RTX 3090 runs Qwen3.6-35B" }));
  const { user } = await renderAt("/records");
  await screen.findByText("共 4 条");
  const box = screen.getByRole("searchbox", { name: "检索" });
  await user.type(box, "Qwen3.6{Enter}");
  expect(await screen.findByText("最相关的 1 条")).toBeInTheDocument();
  expect(bodyRows()[0]).toHaveTextContent("fact:gpu");
  await user.type(box, "{Escape}");
  expect(await screen.findByText("共 4 条")).toBeInTheDocument();

  await user.type(box, "nothing like this{Enter}");
  expect(await screen.findByText("没有匹配的记忆")).toBeInTheDocument();
});

test("opening a row shows its full text and version history; correcting adds a version", async () => {
  const old = memory({ entity_key: "fact:city", content: "Lives in Shanghai", is_current: false });
  const cur = memory({ entity_key: "fact:city", content: "Lives in Suzhou", mutation_type: "evolution", conflict: true });
  db.memories.push(old, cur);
  const { user, router } = await renderAt("/records");
  await user.click(await screen.findByRole("cell", { name: "Lives in Suzhou" }));
  expect(router.state.location.search).toEqual({ memory: cur.memory_id });
  const sheet = await screen.findByRole("dialog", { name: "记忆详情" });
  expect(await within(sheet).findByRole("heading", { name: "版本历史（2）" })).toBeInTheDocument();

  const card = within(sheet).getByRole("region", { name: "fact:city" });
  expect(within(card).getByText("冲突合并")).toBeInTheDocument();
  await user.click(within(card).getByRole("button", { name: "改正" }));
  const area = within(card).getByRole("textbox", { name: "改正后的完整内容" });
  await user.clear(area);
  await user.type(area, "Lives in Hangzhou");
  await user.click(within(card).getByRole("button", { name: "保存为新版本" }));
  expect(await within(sheet).findByRole("heading", { name: "版本历史（3）" })).toBeInTheDocument();
  expect(router.state.location.search).not.toEqual({ memory: cur.memory_id });
});

test("archiving a record closes the detail and drops it from the table", async () => {
  db.memories.push(memory({ entity_key: "fact:a", content: "keep me" }), memory({ entity_key: "fact:b", content: "drop me" }));
  const { user } = await renderAt("/records");
  await user.click(await screen.findByRole("cell", { name: "drop me" }));
  const card = await screen.findByRole("region", { name: "fact:b" });
  await user.click(within(card).getByRole("button", { name: "归档" }));
  await user.type(within(card).getByRole("textbox", { name: "归档原因" }), "obsolete");
  await user.click(within(card).getByRole("button", { name: "确认归档" }));
  expect(await screen.findByText("共 1 条")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.queryByRole("cell", { name: "drop me" })).not.toBeInTheDocument();
});

test("a memory linked from the command palette opens directly", async () => {
  const m = memory({ entity_key: "fact:linked", content: "opened by link" });
  db.memories.push(m);
  await renderAt(`/records?memory=${m.memory_id}`);
  expect(await screen.findByRole("region", { name: "fact:linked" })).toBeInTheDocument();
});
