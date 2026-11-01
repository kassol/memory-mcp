import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, reset } from "@/test/server";

beforeEach(() => {
  reset();
});

async function openStartup() {
  const view = await renderAt("/settings");
  await view.user.click(await screen.findByRole("tab", { name: "启动设置" }));
  return view;
}

const card = async () => (await screen.findByText("启动设置", { selector: "[data-slot=card-title]" })).closest("[data-slot=card]") as HTMLElement;

test("effective values are shown with the manual restart notice outside a container", async () => {
  await openStartup();
  const region = await card();
  expect(within(region).getByText("手工运行")).toBeInTheDocument();
  expect(within(region).getByText(/没有容器重启策略/)).toBeInTheDocument();
  expect(within(region).getByLabelText("端口")).toHaveValue("8765");
  expect(within(region).getByLabelText("数据目录")).toHaveValue("/app/data");
  expect(within(region).getByText(/openai\/text-embedding-3-small · 1536 维/)).toBeInTheDocument();
  expect(within(region).getByText(/上次应用：/)).toBeInTheDocument();
});

test("inside a container the port and data directory are read-only with the reason", async () => {
  db.startup.container = true;
  db.startup.read_only = { port: "端口由容器编排决定", data_dir: "数据目录由容器编排挂载" };
  db.startup.editable = ["vector_backend", "debug"];
  await openStartup();
  const region = await card();
  expect(within(region).getByText("容器里运行")).toBeInTheDocument();
  expect(within(region).getByLabelText("端口")).toHaveAttribute("readonly");
  expect(within(region).getByText("端口由容器编排决定")).toBeInTheDocument();
});

test("only changed values are saved as the draft", async () => {
  const { user } = await openStartup();
  const region = await card();
  const port = within(region).getByLabelText("端口");
  await user.clear(port);
  await user.type(port, "9000");
  await user.click(within(region).getByRole("button", { name: "保存为待生效" }));

  await waitFor(() =>
    expect(db.calls.find((c) => c.method === "PUT" && c.path === "/api/v1/startup-settings")).toMatchObject({
      body: { port: 9000 },
    }),
  );
  expect(await within(region).findByText(/待生效：/)).toBeInTheDocument();
  expect(within(region).getByText(/port = 9000/)).toBeInTheDocument();
});

test("check reports every problem with its reason", async () => {
  db.startup.draft = { data_dir: "/bad/place" };
  const { user } = await openStartup();
  const region = await card();
  await user.click(within(region).getByRole("button", { name: "校验" }));
  expect(await within(region).findByText("校验未通过")).toBeInTheDocument();
  expect(within(region).getByText("数据目录不存在：/bad/place")).toBeInTheDocument();
});

test("applying restarts the service and reports the result", async () => {
  db.startup.draft = { debug: true };
  const { user } = await openStartup();
  const region = await card();
  await user.click(within(region).getByRole("button", { name: "应用并重启" }));
  await waitFor(() => expect(db.calls.find((c) => c.path === "/api/v1/startup-settings/apply")?.method).toBe("POST"));
  // The page waits for the process to go away, then for it to come back, then re-reads the settings.
  expect(await within(region).findByText("重启中…")).toBeInTheDocument();
  expect(await within(region).findByText("已生效", {}, { timeout: 10000 })).toBeInTheDocument();
  expect(db.startup.effective.debug).toBe(true);
  expect(db.startup.draft).toEqual({});
});
