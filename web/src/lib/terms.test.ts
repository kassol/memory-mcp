import { expect, test } from "vitest";

import { shanghaiDay, shortDay, shortWhen, when } from "@/lib/terms";

test("timestamps render in Beijing time, not UTC or the browser zone", () => {
  expect(when("2026-11-02T16:00:00+00:00")).toBe("2026-11-03 00:00");
  expect(when("2026-11-02T15:59:00Z")).toBe("2026-11-02 23:59");
  expect(when("2026-11-03T00:00:00+08:00")).toBe("2026-11-03 00:00");
  expect(when(null)).toBe("");
});

test("short forms keep the Beijing day and year", () => {
  expect(shortDay("2026-11-02T16:00:00+00:00")).toBe("11-03");
  expect(shanghaiDay(Date.parse("2026-11-02T16:00:00+00:00"))).toBe("2026-11-03");
  const year = new Date().getUTCFullYear();
  expect(shortWhen(`${year}-11-02T16:00:00+00:00`)).toBe("11-03 00:00");
  expect(shortWhen("2025-06-01T00:00:00+00:00")).toBe("25-06-01 08:00");
});
