import type { Setting } from "@/lib/types";

/** Reason the draft cannot be saved, or "" when it can. Mirrors the server's validation. */
export function invalidReason(s: Setting, draft: string): string {
  if (!draft.trim()) return "请填写数值";
  const n = Number(draft);
  if (!Number.isFinite(n)) return "需要是数字";
  if (s.type === "int" && !Number.isInteger(n)) return "需要是整数";
  if (n < s.min || n > s.max) return `超出范围 ${s.min} – ${s.max}`;
  return "";
}
