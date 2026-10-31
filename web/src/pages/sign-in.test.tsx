import { screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, reset, TOKEN } from "@/test/server";

beforeEach(reset);

test("without a token only the sign-in form shows and no data is requested", async () => {
  await renderAt("/docket", { signedIn: false });
  expect(await screen.findByRole("heading", { name: "输入访问令牌" })).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "页面" })).not.toBeInTheDocument();
  expect(db.calls).toEqual([]);
});

test("a wrong token shows an error and keeps the form", async () => {
  const { user } = await renderAt("/docket", { signedIn: false });
  await user.type(await screen.findByLabelText("令牌"), "wrong");
  await user.click(screen.getByRole("button", { name: "进入" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("令牌无效");
  expect(screen.getByLabelText("令牌")).toHaveValue("");
  expect(sessionStorage.getItem("memory-mcp.access-token")).toBeNull();
});

test("the right token opens the docket and stays in this tab only", async () => {
  const { user } = await renderAt("/docket", { signedIn: false });
  await user.type(await screen.findByLabelText("令牌"), TOKEN);
  await user.click(screen.getByRole("button", { name: "进入" }));
  expect(await screen.findByRole("navigation", { name: "页面" })).toBeInTheDocument();
  expect(await screen.findByText("没有待审的发现")).toBeInTheDocument();
  expect(sessionStorage.getItem("memory-mcp.access-token")).toBe(TOKEN);
});

test("signing out returns to the sign-in form and forgets the token", async () => {
  const { user } = await renderAt("/docket");
  await screen.findByText("没有待审的发现");
  await user.click(screen.getAllByRole("button", { name: "退出" })[0]);
  expect(await screen.findByRole("heading", { name: "输入访问令牌" })).toBeInTheDocument();
  expect(sessionStorage.getItem("memory-mcp.access-token")).toBeNull();
});

test("a token rejected later sends the person back to sign in", async () => {
  sessionStorage.setItem("memory-mcp.access-token", "revoked");
  const { router } = await renderAt("/docket", { signedIn: false });
  await waitFor(() => expect(screen.getByRole("heading", { name: "输入访问令牌" })).toBeInTheDocument());
  expect(screen.getByRole("alert")).toHaveTextContent("令牌无效");
  expect(router.state.location.pathname).toBe("/docket");
});
