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
  correction: "改正",
  reversal: "反转",
  refinement: "补充",
};

export const SOURCE: Record<string, string> = { console: "面板", file: "配置文件", default: "默认值" };

export const when = (iso: string | null | undefined) => (iso ? iso.replace("T", " ").slice(0, 16) : "");

export const caseNo = (index: number) => String(index + 1).padStart(2, "0");
