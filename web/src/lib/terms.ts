// Interface wording for domain terms; see GLOSSARY.md.
export const KIND: Record<string, string> = {
  duplicate: "重复",
  internal_contradiction: "内部矛盾",
  multiple_current: "多条当前版本",
  contradiction: "矛盾",
};

export const MUTATION: Record<string, string> = {
  initial: "初始",
  update: "更新",
  evolution: "演化",
  correction: "人工改正",
  reversal: "反转",
  refinement: "补充",
};

export const SOURCE: Record<string, string> = { console: "面板", file: "配置文件", default: "默认值" };

// Every timestamp in the console is shown in Asia/Shanghai (UTC+8), whatever the browser's zone.
// China has no daylight saving, so a fixed offset is exact for the dates this console holds.
const OFFSET_MS = 8 * 60 * 60 * 1000;

function shanghai(value: string | number | null | undefined) {
  if (value === null || value === undefined) return null;
  const ms = typeof value === "number" ? value : Date.parse(value);
  if (Number.isNaN(ms)) return null;
  const at = new Date(ms + OFFSET_MS);
  return {
    year: at.getUTCFullYear(),
    month: at.getUTCMonth() + 1,
    day: at.getUTCDate(),
    hour: at.getUTCHours(),
    minute: at.getUTCMinutes(),
  };
}

const pad = (value: number) => String(value).padStart(2, "0");
const day = (p: NonNullable<ReturnType<typeof shanghai>>) => `${p.year}-${pad(p.month)}-${pad(p.day)}`;
const clock = (p: NonNullable<ReturnType<typeof shanghai>>) => `${pad(p.hour)}:${pad(p.minute)}`;

export const when = (iso: string | null | undefined) => {
  const p = shanghai(iso);
  return p ? `${day(p)} ${clock(p)}` : "";
};

export const shortWhen = (iso: string | null | undefined) => {
  const p = shanghai(iso);
  if (!p) return "";
  const now = shanghai(Date.now());
  const stamp = `${pad(p.month)}-${pad(p.day)} ${clock(p)}`;
  return now && p.year === now.year ? stamp : `${String(p.year).slice(2)}-${stamp}`;
};

/** MM-DD in Beijing time, for lists that only have room for the day. */
export const shortDay = (iso: string | null | undefined) => {
  const p = shanghai(iso);
  return p ? `${pad(p.month)}-${pad(p.day)}` : "";
};

/** YYYY-MM-DD in Beijing time, for the chart's day buckets. */
export const shanghaiDay = (ms: number) => {
  const p = shanghai(ms);
  return p ? day(p) : "";
};

export const caseNo = (index: number) => String(index + 1).padStart(2, "0");
