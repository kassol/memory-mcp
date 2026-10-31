import { screen, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import { renderAt } from "@/test/render";
import { db, memory, reset } from "@/test/server";

beforeEach(reset);

test("Ctrl+K opens the palette; a page entry navigates there", async () => {
  const { user, router } = await renderAt("/docket");
  await screen.findByText("没有待审的发现");
  await user.keyboard("{Control>}k{/Control}");
  const palette = await screen.findByRole("dialog", { name: "命令面板" });
  await user.type(within(palette).getByRole("combobox"), "设置");
  await user.keyboard("{Enter}");
  expect(router.state.location.pathname).toBe("/settings");
});

test("typing searches memories; Enter opens the chosen one in records", async () => {
  const m = memory({ entity_key: "project:gpu", content: "RTX 3090 runs Qwen3.6" });
  db.memories.push(m);
  const { user, router } = await renderAt("/docket");
  await screen.findByText("没有待审的发现");
  await user.keyboard("{Control>}k{/Control}");
  const palette = await screen.findByRole("dialog", { name: "命令面板" });
  await user.type(within(palette).getByRole("combobox"), "RTX 3090");
  expect(await within(palette).findByText("project:gpu")).toBeInTheDocument();
  await user.keyboard("{Enter}");
  expect(router.state.location.pathname).toBe("/records");
  expect(router.state.location.search).toEqual({ memory: m.memory_id });
  expect(await screen.findByRole("region", { name: "project:gpu" })).toBeInTheDocument();
});

test("results that arrive after typing are highlighted, so Enter opens the first one", async () => {
  const { http, HttpResponse, delay } = await import("msw");
  const { server } = await import("@/test/server");
  const m = memory({ entity_key: "project:late", content: "slow answer" });
  db.memories.push(m);
  server.use(
    http.get("http://localhost:3000/api/v1/memories/search", async () => {
      await delay(150);
      return HttpResponse.json({ ok: true, data: { results: [{ ...m }], total: 1 } });
    }),
  );
  const { user, router } = await renderAt("/settings");
  await screen.findByText("行为参数");
  await user.keyboard("{Control>}k{/Control}");
  const palette = await screen.findByRole("dialog", { name: "命令面板" });
  await user.type(within(palette).getByRole("combobox"), "slow");
  await within(palette).findByText("project:late");
  await user.keyboard("{Enter}");
  expect(router.state.location.search).toEqual({ memory: m.memory_id });
});
