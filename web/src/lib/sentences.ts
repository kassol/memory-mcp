// Sentence-level comparison for memory versions: which sentences the newer text adds and which
// the older text loses. Shared by the record history; the docket keeps its own pair summary.
export interface SentenceDiff {
  added: string[];
  removed: string[];
  shared: number;
}

export function sentences(text: string): string[] {
  return text
    // Chinese stops split directly; Latin stops split only before whitespace, so decimals and
    // version numbers stay in one sentence.
    .split(/(?<=[。！？；\n])|(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

export function diffSentences(older: string, newer: string): SentenceDiff {
  const before = sentences(older);
  const after = sentences(newer);
  const beforeSet = new Set(before);
  const afterSet = new Set(after);
  return {
    added: after.filter((sentence) => !beforeSet.has(sentence)),
    removed: before.filter((sentence) => !afterSet.has(sentence)),
    shared: after.filter((sentence) => beforeSet.has(sentence)).length,
  };
}
