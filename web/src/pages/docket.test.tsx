import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, memory, reset } from "@/test/server";

function seedDuplicate() {
  const a = memory({ entity_key: "fact:city", content: "Lives in Shanghai" });
  const b = memory({ entity_key: "fact:home", content: "Lives in Shanghai, near the river" });
  const c = memory({ entity_key: "tool:editor", content: "Uses vim and also switched to emacs" });
  db.memories.push(a, b, c);
  db.findings.push(
    { id: "f1", kind: "duplicate", memory_id: a.memory_id, other_memory_id: b.memory_id, entity_key: null, detail: "Both say where the owner lives.", status: "open", created_at: "2026-10-30" },
    { id: "f2", kind: "internal_contradiction", memory_id: c.memory_id, other_memory_id: null, entity_key: "tool:editor", detail: "vim and emacs both current.", status: "open", created_at: "2026-10-30" },
  );
  return { a, b, c };
}

const rows = () => within(screen.getByRole("listbox", { name: "待审的发现" })).getAllByRole("option");
const toast = async (text: string) => expect((await screen.findAllByText(text))[0]).toBeInTheDocument();
const docketCount = () => within(screen.getByRole("navigation", { name: "页面" })).getByRole("link", { name: /待审/ }).parentElement!;

beforeEach(reset);

test("the first case opens with both records side by side in full", async () => {
  seedDuplicate();
  await renderAt("/docket");
  expect(await screen.findByRole("heading", { name: "卷宗 01" })).toBeInTheDocument();
  const left = await screen.findByRole("region", { name: "左侧记录" });
  const right = screen.getByRole("region", { name: "右侧记录" });
  expect(within(left).getByText("Lives in Shanghai")).toBeInTheDocument();
  expect(within(right).getByText("Lives in Shanghai, near the river")).toBeInTheDocument();
  expect(screen.getByText("Both say where the owner lives.", { selector: "p" })).toBeInTheDocument();
  expect(rows()).toHaveLength(2);
  await waitFor(() => expect(docketCount()).toHaveTextContent("2"));
});

test("dismissing removes the case and opens the next one", async () => {
  seedDuplicate();
  const { user } = await renderAt("/docket");
  await screen.findByRole("region", { name: "左侧记录" });
  await user.click(screen.getByRole("button", { name: "判为误报" }));
  await toast("已判为误报");
  expect(db.calls.some((c) => c.method === "POST" && c.path === "/api/v1/findings/f1/dismiss")).toBe(true);
  expect(await screen.findByText("vim and emacs both current.", { selector: "p" })).toBeInTheDocument();
  expect(rows()).toHaveLength(1);
  expect(docketCount()).toHaveTextContent("1");
});

test("correcting a record shows the new version in its place", async () => {
  seedDuplicate();
  const { user } = await renderAt("/docket");
  const left = await screen.findByRole("region", { name: "左侧记录" });
  await user.click(within(left).getByRole("button", { name: "改正" }));
  const area = within(left).getByRole("textbox", { name: "改正后的完整内容" });
  await user.clear(area);
  await user.type(area, "Lives in Hangzhou");
  await user.click(within(left).getByRole("button", { name: "保存为新版本" }));
  await toast("已保存改正版本");
  const updated = await screen.findByRole("region", { name: "左侧记录" });
  expect(await within(updated).findByText("Lives in Hangzhou")).toBeInTheDocument();
  expect(within(updated).getByText("改正", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  expect(db.calls.find((c) => c.path.endsWith("/correct"))?.body).toEqual({ content: "Lives in Hangzhou" });
});

test("archiving needs a reason and then marks the record archived", async () => {
  seedDuplicate();
  const { user } = await renderAt("/docket");
  const right = await screen.findByRole("region", { name: "右侧记录" });
  await user.click(within(right).getByRole("button", { name: "归档" }));
  await user.click(within(right).getByRole("button", { name: "确认归档" }));
  await toast("请填写归档原因");
  expect(db.calls.some((c) => c.path.endsWith("/archive"))).toBe(false);

  await user.type(within(right).getByRole("textbox", { name: "归档原因" }), "same as the other");
  await user.click(within(right).getByRole("button", { name: "确认归档" }));
  await toast("已归档");
  await waitFor(() => expect(within(screen.getByRole("region", { name: "右侧记录" })).getByText("已失效")).toBeInTheDocument());
  expect(screen.getByText("归档原因：same as the other")).toBeInTheDocument();
});

test("keyboard shortcuts move between cases and rule on them", async () => {
  seedDuplicate();
  const { user } = await renderAt("/docket");
  await screen.findByRole("heading", { name: "卷宗 01" });
  await user.keyboard("j");
  expect(await screen.findByRole("heading", { name: "卷宗 02" })).toBeInTheDocument();
  await user.keyboard("k");
  expect(await screen.findByRole("heading", { name: "卷宗 01" })).toBeInTheDocument();

  await screen.findByRole("region", { name: "右侧记录" });
  await user.keyboard("{Shift>}a{/Shift}");
  const right = screen.getByRole("region", { name: "右侧记录" });
  expect(within(right).getByRole("textbox", { name: "归档原因" })).toHaveFocus();
  await user.keyboard("d"); // typing in the editor is not a shortcut
  expect(db.calls.some((c) => c.path.endsWith("/dismiss"))).toBe(false);
  await user.click(within(right).getByRole("button", { name: "取消" }));

  await user.keyboard("d");
  await toast("已判为误报");
  expect(db.calls.some((c) => c.path === "/api/v1/findings/f1/dismiss")).toBe(true);
});

test("C and A do nothing on an archived record, and the other shortcuts keep working", async () => {
  seedDuplicate();
  const { user } = await renderAt("/docket");
  const left = await screen.findByRole("region", { name: "左侧记录" });
  await user.click(within(left).getByRole("button", { name: "归档" }));
  await user.type(within(left).getByRole("textbox", { name: "归档原因" }), "dup");
  await user.click(within(left).getByRole("button", { name: "确认归档" }));
  await waitFor(() => expect(within(screen.getByRole("region", { name: "左侧记录" })).getByText("已失效")).toBeInTheDocument());

  await user.keyboard("a");
  expect(screen.queryByRole("textbox", { name: "归档原因" })).not.toBeInTheDocument();
  await user.keyboard("j");
  expect(await screen.findByRole("heading", { name: "卷宗 02" })).toBeInTheDocument();
});

test("an empty docket says so", async () => {
  await renderAt("/docket");
  expect(await screen.findByText("没有待审的发现")).toBeInTheDocument();
});
