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

/** An access token as listed; the value appears only in the create response. */
export interface AccessToken {
  id: string;
  name: string;
  /** "file": the initial token from the configuration file; "console": created here. */
  source: "file" | "console";
  created_at: string;
  last_used_at: string | null;
  /** Revoked, or for the initial token, disabled. */
  revoked_at: string | null;
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
