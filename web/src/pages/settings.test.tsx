import { screen, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, reset, setting } from "@/test/server";

const toast = async (text: string) => expect((await screen.findAllByText(text))[0]).toBeInTheDocument();

beforeEach(() => {
  reset();
  db.settings.push(
    setting({ key: "maintenance_max_llm_calls", label: "维护单轮模型调用上限", group: "behaviour", type: "int", default: 100, value: 100, min: 0, max: 1000, recommended: null, note: null }),
    setting({ key: "fts_weight", label: "全文检索权重", note: "全文 ×2 时 14 条" }),
    setting({ key: "rrf_k", label: "RRF 常数 k", type: "int", default: 60, value: 60, recommended: 60, min: 1, max: 1000, file_value: 60, source: "file" }),
  );
});

const row = (label: string) => screen.getByLabelText(label).closest("li") as HTMLElement;

test("settings are grouped with their source, range and evaluation note", async () => {
  await renderAt("/settings");
  expect(await screen.findByRole("heading", { name: "行为参数" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "高级参数" })).toBeInTheDocument();
  const fts = row("全文检索权重");
  expect(within(fts).getByText("默认值")).toBeInTheDocument();
  expect(within(fts).getByText(/全文 ×2 时 14 条/)).toBeInTheDocument();
  expect(within(fts).getByText("范围 0 – 10")).toBeInTheDocument();
  expect(within(row("RRF 常数 k")).getByText("配置文件")).toBeInTheDocument();
});

test("an out-of-range value is rejected before saving", async () => {
  const { user } = await renderAt("/settings");
  const input = await screen.findByLabelText("全文检索权重");
  await user.clear(input);
  await user.type(input, "11");
  expect(within(row("全文检索权重")).getByRole("alert")).toHaveTextContent("超出范围 0 – 10");
  expect(within(row("全文检索权重")).getByRole("button", { name: "保存" })).toBeDisabled();
  await user.clear(input);
  await user.type(input, "1.5");
  expect(within(row("全文检索权重")).queryByRole("alert")).not.toBeInTheDocument();
  expect(within(row("全文检索权重")).getByText("范围 0 – 10")).toBeInTheDocument();
  const budget = await screen.findByLabelText("维护单轮模型调用上限");
  await user.clear(budget);
  await user.type(budget, "2.5");
  expect(within(row("维护单轮模型调用上限")).getByRole("alert")).toHaveTextContent("需要是整数");
  expect(db.calls.filter((c) => c.method === "PUT")).toEqual([]);
});

test("saving a tuning value marks it as a console value and warns it departs from the recommendation", async () => {
  const { user } = await renderAt("/settings");
  const input = await screen.findByLabelText("全文检索权重");
  await user.clear(input);
  await user.type(input, "1");
  await user.click(within(row("全文检索权重")).getByRole("button", { name: "保存" }));
  await toast("全文检索权重已保存");
  expect(db.calls.find((c) => c.method === "PUT")).toMatchObject({ path: "/api/v1/settings/fts_weight", body: { value: 1 } });
  const fts = row("全文检索权重");
  expect(within(fts).getByText("面板")).toBeInTheDocument();
  expect(within(fts).getByText(/与推荐值不同/)).toBeInTheDocument();

  await user.click(within(fts).getByRole("button", { name: "恢复推荐值" }));
  await toast("全文检索权重已保存");
  expect(screen.getByLabelText("全文检索权重")).toHaveValue("2");
  expect(within(row("全文检索权重")).queryByText(/与推荐值不同/)).not.toBeInTheDocument();
});

test("revert drops the console value and shows the file value again", async () => {
  db.settings[2] = { ...db.settings[2], value: 30, source: "console" };
  const { user } = await renderAt("/settings");
  const rrf = await screen.findByLabelText("RRF 常数 k");
  expect(rrf).toHaveValue("30");
  await user.click(within(row("RRF 常数 k")).getByRole("button", { name: "恢复为配置文件值" }));
  await toast("RRF 常数 k已恢复为配置文件");
  expect(screen.getByLabelText("RRF 常数 k")).toHaveValue("60");
  expect(within(row("RRF 常数 k")).getByText("配置文件")).toBeInTheDocument();
  expect(db.calls.find((c) => c.method === "DELETE")?.path).toBe("/api/v1/settings/rrf_k");
});
