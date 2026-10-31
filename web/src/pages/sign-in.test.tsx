import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, PASSWORD, reset, TOKEN } from "@/test/server";

beforeEach(reset);

const nav = () => screen.queryByRole("navigation", { name: "页面" });
const dataCalls = () => db.calls.filter((c) => !c.path.startsWith("/api/v1/console/"));

test("signed out: the password form only, and no data is requested", async () => {
  db.session = "none";
  await renderAt("/docket");
  expect(await screen.findByRole("heading", { name: "登录" })).toBeInTheDocument();
  expect(nav()).not.toBeInTheDocument();
  expect(dataCalls()).toEqual([]);
});

test("a wrong password shows an error; the right one opens the docket", async () => {
  db.session = "none";
  const { user } = await renderAt("/docket");
  await user.type(await screen.findByLabelText("管理口令"), "wrong");
  await user.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("口令错误");
  expect(screen.getByLabelText("管理口令")).toHaveValue("");

  await user.type(screen.getByLabelText("管理口令"), PASSWORD);
  await user.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByRole("navigation", { name: "页面" })).toBeInTheDocument();
  expect(await screen.findByText("没有待审的发现")).toBeInTheDocument();
  expect(db.calls.filter((c) => c.path === "/api/v1/console/login").map((c) => c.body)).toEqual([{ password: "wrong" }, { password: PASSWORD }]);
});

test("first run: the access token signs in once, then the admin password must be set", async () => {
  db.password = null;
  db.session = "none";
  const { user } = await renderAt("/docket");
  expect(await screen.findByRole("heading", { name: "首次登录" })).toBeInTheDocument();
  await user.type(screen.getByLabelText("访问令牌"), "wrong");
  await user.click(screen.getByRole("button", { name: "继续" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("令牌无效");

  await user.type(screen.getByLabelText("访问令牌"), TOKEN);
  await user.click(screen.getByRole("button", { name: "继续" }));
  expect(await screen.findByRole("heading", { name: "设置管理口令" })).toBeInTheDocument();
  expect(nav()).not.toBeInTheDocument();
  expect(dataCalls()).toEqual([]);

  await user.type(screen.getByLabelText("管理口令"), "new-one");
  await user.type(screen.getByLabelText("再输入一次"), "new-two");
  await user.click(screen.getByRole("button", { name: "保存并进入" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("两次输入的口令不一致");

  await user.clear(screen.getByLabelText("再输入一次"));
  await user.type(screen.getByLabelText("再输入一次"), "new-one");
  await user.click(screen.getByRole("button", { name: "保存并进入" }));
  expect(await screen.findByRole("navigation", { name: "页面" })).toBeInTheDocument();
  expect(db.password).toBe("new-one");
});

test("signing out returns to the password form", async () => {
  const { user } = await renderAt("/docket");
  await screen.findByText("没有待审的发现");
  await user.click(screen.getByRole("button", { name: "退出" }));
  expect(await screen.findByRole("heading", { name: "登录" })).toBeInTheDocument();
  expect(db.session).toBe("none");
});

test("a session that ends while in use sends the person back to sign in", async () => {
  const { router } = await renderAt("/records");
  await screen.findByRole("navigation", { name: "页面" });
  db.session = "none";
  await router.navigate({ to: "/settings" });
  await waitFor(() => expect(screen.getByRole("heading", { name: "登录" })).toBeInTheDocument());
});

test("security settings: change the password and sign out everywhere", async () => {
  const { user } = await renderAt("/settings");
  await user.click(await screen.findByRole("tab", { name: "安全" }));
  const card = screen.getByText("管理口令", { selector: "[data-slot=card-title]" }).closest("[data-slot=card]") as HTMLElement;
  await user.type(within(card).getByLabelText("当前口令"), "wrong");
  await user.type(within(card).getByLabelText("新口令"), "next");
  await user.type(within(card).getByLabelText("再输入一次新口令"), "next");
  await user.click(within(card).getByRole("button", { name: "更新口令" }));
  expect(await within(card).findByRole("alert")).toHaveTextContent("当前口令错误");

  // A refused change keeps what was typed; only the current password needs fixing.
  await user.clear(within(card).getByLabelText("当前口令"));
  await user.type(within(card).getByLabelText("当前口令"), PASSWORD);
  await user.click(within(card).getByRole("button", { name: "更新口令" }));
  expect((await screen.findAllByText("管理口令已更新"))[0]).toBeInTheDocument();
  expect(db.password).toBe("next");

  await user.click(screen.getByRole("button", { name: "退出所有设备" }));
  expect(await screen.findByRole("heading", { name: "登录" })).toBeInTheDocument();
  expect(db.calls.some((c) => c.method === "DELETE" && c.path === "/api/v1/console/sessions")).toBe(true);
});
