import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, reset } from "@/test/server";

beforeEach(() => {
  reset();
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
    last_call_at: "2026-11-01T09:30:00+00:00",
    last_call_ok: false,
    last_call_error: "对话：HTTP 401：invalid x-api-key",
    created_at: "2026-11-01T09:00:00+00:00",
    deletable: true,
  });
});

async function openProviders() {
  const view = await renderAt("/settings");
  await view.user.click(await screen.findByRole("tab", { name: "Provider" }));
  return view;
}

const row = async (name: string) =>
  (await screen.findByText(name, { selector: "td div" })).closest("tr") as HTMLElement;

test("providers are listed with source, protocol, key tail and last call", async () => {
  await openProviders();
  expect(within(await row("openrouter")).getByText("配置文件")).toBeInTheDocument();
  expect(within(await row("openrouter")).getByText("OpenAI 兼容")).toBeInTheDocument();
  expect(within(await row("openrouter")).getByText("成功")).toBeInTheDocument();

  const anthropic = await row("anthropic-direct");
  expect(within(anthropic).getByText("面板")).toBeInTheDocument();
  expect(within(anthropic).getByText("····abcd")).toBeInTheDocument();
  expect(within(anthropic).getByText("失败")).toBeInTheDocument();
  expect(within(anthropic).getByText(/invalid x-api-key/)).toBeInTheDocument();
});

test("adding a provider posts name, protocol, address and key", async () => {
  const { user } = await openProviders();
  await user.click(await screen.findByRole("button", { name: "添加 Provider" }));
  const dialog = await screen.findByRole("dialog");
  await user.type(within(dialog).getByLabelText("名称"), "gemini");
  await user.type(within(dialog).getByLabelText("地址"), "https://generativelanguage.googleapis.com/v1beta");
  await user.type(within(dialog).getByLabelText("API key"), "sk-gemini-5678");
  await user.click(within(dialog).getByRole("button", { name: "添加" }));

  expect(await screen.findByText("gemini", { selector: "td div" })).toBeInTheDocument();
  expect(db.calls.find((c) => c.method === "POST" && c.path === "/api/v1/providers")).toMatchObject({
    body: {
      name: "gemini",
      protocol: "openai",
      base_url: "https://generativelanguage.googleapis.com/v1beta",
      api_key: "sk-gemini-5678",
    },
  });
});

test("tests the connection before saving and shows the result", async () => {
  const { user } = await openProviders();
  await user.click(await screen.findByRole("button", { name: "添加 Provider" }));
  const dialog = await screen.findByRole("dialog");
  await user.type(within(dialog).getByLabelText("地址"), "https://api.example.com/v1");
  await user.type(within(dialog).getByLabelText("API key"), "sk-test-9999");
  await user.click(within(dialog).getByRole("button", { name: "测试连接" }));
  expect(await within(dialog).findByText(/连接成功（用 gpt-4o-mini 试调用），可列出 2 个模型/)).toBeInTheDocument();
  expect(db.calls.find((c) => c.path === "/api/v1/providers/test")).toMatchObject({
    body: { base_url: "https://api.example.com/v1", api_key: "sk-test-9999" },
  });

  await user.clear(within(dialog).getByLabelText("地址"));
  await user.type(within(dialog).getByLabelText("地址"), "https://fail.example.com/v1");
  await user.click(within(dialog).getByRole("button", { name: "测试连接" }));
  expect(await within(dialog).findByText(/HTTP 401/)).toBeInTheDocument();
});

test("editing without a new key keeps the stored one", async () => {
  const { user } = await openProviders();
  const target = await row("anthropic-direct");
  await user.click(within(target).getByRole("button", { name: "编辑" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByPlaceholderText(/已保存 ····abcd/)).toBeInTheDocument();
  await user.clear(within(dialog).getByLabelText("地址"));
  await user.type(within(dialog).getByLabelText("地址"), "https://proxy.example.com/v1");
  await user.click(within(dialog).getByRole("button", { name: "保存" }));

  const call = db.calls.find((c) => c.method === "PUT");
  expect(call?.path).toBe("/api/v1/providers/p1");
  expect(call?.body).toEqual({ base_url: "https://proxy.example.com/v1" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the configuration-file provider cannot be deleted, and its override can be reverted", async () => {
  db.providers[0].base_url = "https://proxy.local/v1";
  db.providers[0].overridden.base_url = true;
  const { user } = await openProviders();
  const file = await row("openrouter");
  expect(within(file).queryByRole("button", { name: "删除" })).not.toBeInTheDocument();

  await user.click(within(file).getByRole("button", { name: "恢复地址" }));
  expect(db.calls.find((c) => c.method === "PUT")?.body).toEqual({ base_url: null });
  expect(await within(await row("openrouter")).findByText("https://openrouter.ai/api/v1")).toBeInTheDocument();
});

test("deleting a console provider asks first", async () => {
  const { user } = await openProviders();
  const target = await row("anthropic-direct");
  await user.click(within(target).getByRole("button", { name: "删除" }));
  const dialog = await screen.findByRole("alertdialog");
  await user.click(within(dialog).getByRole("button", { name: "删除" }));
  await waitFor(() => expect(screen.queryByText("anthropic-direct")).not.toBeInTheDocument());
  expect(db.calls.find((c) => c.method === "DELETE")?.path).toBe("/api/v1/providers/p1");
  expect(await screen.findByText("openrouter", { selector: "td div" })).toBeInTheDocument();
});
