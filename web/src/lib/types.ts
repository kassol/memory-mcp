export type FindingKind = "duplicate" | "internal_contradiction" | "multiple_current" | "contradiction";

export interface Finding {
  id: string;
  kind: FindingKind;
  memory_id: string;
  other_memory_id: string | null;
  entity_key: string | null;
  detail: string | null;
  status: string;
  created_at: string;
}

export interface MemoryView {
  memory_id: string;
  entity_key: string;
  entity_type: string;
  content: string;
  mutation_type: string;
  created_at: string;
  valid_from: string;
  is_current: boolean;
  conflict: boolean;
  archived_reason: string | null;
}

export interface MemoryRecord extends MemoryView {
  versions: MemoryView[];
}

/** One row of the records list or of a search result. */
export interface MemoryItem {
  memory_id: string;
  entity_key: string;
  entity_type: string;
  content: string;
  created_at: string;
  /** Present in the records list, absent in search results. */
  valid_from?: string;
}

export type SettingSource = "console" | "file" | "default";

export interface Setting {
  key: string;
  label: string;
  group: "behaviour" | "advanced";
  type: "int" | "float";
  description: string;
  default: number;
  min: number;
  max: number;
  recommended: number | null;
  note: string | null;
  value: number;
  source: SettingSource;
  file_value: number | null;
}
