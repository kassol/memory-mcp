import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, reset } from "@/test/server";

beforeEach(() => {
  reset();
});

async function openRoles() {
  const view = await renderAt("/settings");
  await view.user.click(await screen.findByRole("tab", { name: "模型用途" }));
  return view;
}

const card = async () => (await screen.findByText("模型用途", { selector: "h3, [data-slot=card-title]" })).closest("[data-slot=card]") as HTMLElement;

test("the write and maintenance roles show their defaults, and the vector role is read-only", async () => {
  await openRoles();
  const region = await card();
  expect(within(region).getAllByText("默认")).toHaveLength(2);
  expect(within(region).getAllByText(/openrouter · deepseek\/deepseek-v4\.1-flash-1017 · 30 秒/)).toHaveLength(2);

  const vector = within(region).getByText("向量").closest("div") as HTMLElement;
  expect(within(vector).getByText("只读")).toBeInTheDocument();
  // Only the two configurable roles have an editor: provider picker, model field, timeout field.
  expect(within(region).getAllByLabelText(/用途的 Provider/)).toHaveLength(2);
  expect(within(region).queryByLabelText("向量用途的 Provider")).not.toBeInTheDocument();
});

test("saving a role posts the provider, model and timeout and marks it custom", async () => {
  db.providers.push({
    id: "p1",
    name: "anthropic-direct",
    protocol: "anthropic",
    base_url: "https://api.anthropic.com/v1",
    source: "console",
    has_key: true,
    api_key_last4: "abcd",
    overridden: { base_url: false, api_key: false },
    file_base_url: null,
    file_api_key_last4: null,
    last_call_at: null,
    last_call_ok: null,
    last_call_error: null,
    created_at: "2026-11-01T09:00:00+00:00",
    deletable: true,
  });
  const { user } = await openRoles();
  const region = await card();
  await user.click(within(region).getAllByRole("combobox")[0]);
  await user.click(await screen.findByRole("option", { name: "anthropic-direct" }));
  const modelField = within(region).getAllByLabelText("模型")[0];
  await user.clear(modelField);
  await user.type(modelField, "claude-3-5-haiku");
  await user.click(within(region).getAllByRole("button", { name: "保存" })[0]);

  await waitFor(() =>
    expect(db.calls.find((c) => c.method === "PUT" && c.path === "/api/v1/model-roles/write")).toMatchObject({
      body: { provider_id: "p1", model: "claude-3-5-haiku", timeout: 30 },
    }),
  );
  expect(await within(region).findByText("自定义")).toBeInTheDocument();
});

test("a role can be tested and reverts to its defaults", async () => {
  db.roles[0] = { ...db.roles[0], model: "custom-model", custom: true };
  const { user } = await openRoles();
  const region = await card();
  await user.click(within(region).getAllByRole("button", { name: "测试调用" })[0]);
  expect(await within(region).findByText("调用成功：OK")).toBeInTheDocument();
  expect(db.calls.find((c) => c.path === "/api/v1/model-roles/write/test")?.method).toBe("POST");

  await user.click(within(region).getByRole("button", { name: "恢复默认" }));
  await waitFor(() => expect(db.calls.find((c) => c.method === "DELETE")?.path).toBe("/api/v1/model-roles/write"));
  expect(await within(region).findAllByText("默认")).toHaveLength(2);
});

test("a failing test call shows the reason", async () => {
  db.providers.push({
    id: "p2",
    name: "broken",
    protocol: "openai",
    base_url: "https://fail.example.com/v1",
    source: "console",
    has_key: true,
    api_key_last4: "wxyz",
    overridden: { base_url: false, api_key: false },
    file_base_url: null,
    file_api_key_last4: null,
    last_call_at: null,
    last_call_ok: null,
    last_call_error: null,
    created_at: "2026-11-01T09:00:00+00:00",
    deletable: true,
  });
  db.roles[1] = { ...db.roles[1], provider_id: "p2", provider_name: "broken", custom: true };
  const { user } = await openRoles();
  const region = await card();
  await user.click(within(region).getAllByRole("button", { name: "测试调用" })[1]);
  expect(await within(region).findByText(/HTTP 401/)).toBeInTheDocument();
});
