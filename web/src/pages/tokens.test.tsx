import { screen, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, reset } from "@/test/server";

beforeEach(() => {
  reset();
  db.tokens.push(
    { id: "t1", name: "laptop", source: "console", created_at: "2026-10-31T09:00:00+00:00", last_used_at: null, revoked_at: null },
    { id: "t2", name: "old-host", source: "console", created_at: "2026-10-30T09:00:00+00:00", last_used_at: "2026-10-30T10:00:00+00:00", revoked_at: "2026-10-31T10:00:00+00:00" },
  );
});

async function openTokens() {
  const view = await renderAt("/settings");
  await view.user.click(await screen.findByRole("tab", { name: "访问令牌" }));
  return view;
}

// The name cell also carries the state badge, so find the row by the name text.
const row = (name: string) => screen.getByText(name, { selector: "td div" }).closest("tr") as HTMLElement;
const findName = (name: string) => screen.findByText(name, { selector: "td div" });

test("tokens are listed with source, last use and state", async () => {
  await openTokens();
  expect(await findName("laptop")).toBeInTheDocument();
  expect(within(row("initial")).getByText("配置文件")).toBeInTheDocument();
  expect(within(row("initial")).getByText("2026-11-01 17:30")).toBeInTheDocument();
  expect(within(row("laptop")).getByText("从未使用")).toBeInTheDocument();
  expect(within(row("old-host")).getByText("已吊销")).toBeInTheDocument();
  expect(within(row("old-host")).queryByRole("button")).not.toBeInTheDocument();
});

test("a new token's value is shown once, then only its name remains", async () => {
  const { user } = await openTokens();
  await user.type(await screen.findByLabelText("名称"), "ci-runner");
  await user.click(screen.getByRole("button", { name: "创建令牌" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByDisplayValue("value-of-ci-runner")).toBeInTheDocument();
  expect(within(dialog).getByText(/只显示这一次/)).toBeInTheDocument();
  expect(db.calls.find((c) => c.method === "POST")).toMatchObject({ path: "/api/v1/tokens", body: { name: "ci-runner" } });

  await user.click(within(dialog).getByRole("button", { name: "我已保存" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(await findName("ci-runner")).toBeInTheDocument();
  expect(screen.queryByDisplayValue("value-of-ci-runner")).not.toBeInTheDocument();
});

test("a duplicate name shows the reason and creates nothing", async () => {
  const { user } = await openTokens();
  await user.type(await screen.findByLabelText("名称"), "laptop");
  await user.click(screen.getByRole("button", { name: "创建令牌" }));
  expect(await screen.findByText("名称已被使用：laptop")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("revoking a token asks first, then marks it revoked", async () => {
  const { user } = await openTokens();
  await findName("laptop");
  await user.click(within(row("laptop")).getByRole("button", { name: "吊销" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(within(dialog).getByText(/laptop/)).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "吊销" }));
  expect(await within(row("laptop")).findByText("已吊销")).toBeInTheDocument();
  expect(db.calls.find((c) => c.method === "DELETE")?.path).toBe("/api/v1/tokens/t1");
});

test("the initial token is revoked like any other, with a warning about the clients that use it", async () => {
  const { user } = await openTokens();
  await findName("initial");
  await user.click(within(row("initial")).getByRole("button", { name: "吊销" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(within(dialog).getByText(/维护定时任务/)).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "吊销" }));
  expect(await within(row("initial")).findByText("已吊销")).toBeInTheDocument();
  expect(within(row("initial")).queryByRole("button")).not.toBeInTheDocument();
  expect(db.calls.find((c) => c.method === "DELETE")?.path).toBe("/api/v1/tokens/initial");
});
