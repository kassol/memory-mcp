// Records view state lives in the URL: a refresh, a back step, or a shared link keeps the
// filters, the sort, the page and the open record.
export interface RecordsSearch {
  memory?: string;
  view?: "log";
  q?: string;
  type?: string;
  key?: string;
  sort?: string;
  page?: number;
}

export const SORTS = [
  { value: "created_at:desc", label: "最新写入" },
  { value: "created_at:asc", label: "最早写入" },
  { value: "valid_from:asc", label: "最久未更新" },
  { value: "valid_from:desc", label: "最近更新" },
  { value: "entity_key:asc", label: "Key A–Z" },
];

export const DEFAULT_SORT = SORTS[0].value;

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Read the address into a shape the page can trust; unknown values fall back to the defaults. */
export function parseRecordsSearch(search: Record<string, unknown>): RecordsSearch {
  const out: RecordsSearch = {};
  const memory = text(search.memory);
  if (memory) out.memory = memory;
  if (search.view === "log") out.view = "log";
  const q = text(search.q);
  if (q) out.q = q;
  const type = text(search.type);
  if (type) out.type = type;
  const key = text(search.key);
  if (key) out.key = key;
  const sort = text(search.sort);
  if (sort && SORTS.some((s) => s.value === sort)) out.sort = sort;
  // Pages are 1-based in the address and 0-based in the page, so the link reads naturally.
  const page = Number(search.page);
  if (Number.isInteger(page) && page > 1) out.page = page - 1;
  return out;
}

/** Drop blanks and defaults so the address stays short and stable. */
export function cleanRecordsSearch(search: RecordsSearch): RecordsSearch {
  const out: RecordsSearch = {};
  if (search.memory) out.memory = search.memory;
  if (search.view === "log") out.view = "log";
  if (search.q) out.q = search.q;
  if (search.type) out.type = search.type;
  if (search.key) out.key = search.key;
  if (search.sort && search.sort !== DEFAULT_SORT) out.sort = search.sort;
  if (search.page && search.page > 0) out.page = search.page + 1;
  return out;
}
