// One record: full text, stamps, and the inline correct / archive editors.
import { useForm } from "@tanstack/react-form";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Stamp } from "@/components/registry";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, enc, failed } from "@/lib/api";
import { MUTATION, when } from "@/lib/terms";
import type { MemoryRecord, MemoryView } from "@/lib/types";

export type EditMode = "correct" | "archive" | null;

export function RecordStamps({ r }: { r: MemoryView }) {
  return (
    <>
      {r.is_current ? <Stamp tone="current">当前</Stamp> : <Stamp tone="archived">已失效</Stamp>}
      {r.mutation_type === "correction" && <Stamp tone="correction">改正</Stamp>}
      {r.conflict && <Stamp tone="conflict">冲突合并</Stamp>}
    </>
  );
}

function Editor({ hint, children }: { hint: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-2 border-t border-rule px-3.5 pt-3 pb-3.5">
      <p className="m-0 text-sm text-ink-2">{hint}</p>
      {children}
    </div>
  );
}

function CorrectForm({ r, onDone, onCancel }: { r: MemoryRecord; onDone: (next: MemoryView) => void; onCancel: () => void }) {
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => area.current?.focus(), []);
  const form = useForm({
    defaultValues: { content: r.content },
    onSubmit: async ({ value }) => {
      if (!value.content.trim()) {
        toast.error("内容不能为空");
        return;
      }
      try {
        const next = await api<MemoryView>(`/memories/${enc(r.memory_id)}/correct`, {
          method: "POST",
          body: { content: value.content },
        });
        toast.success("已保存改正版本");
        onDone(next);
      } catch (error) {
        failed(error);
      }
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void form.handleSubmit();
      }}
    >
      <Editor hint="保存后原文变为历史版本。这里写的内容原样替换，不经过自动合并。">
        <form.Field name="content">
          {(field) => (
            <Textarea
              ref={area}
              aria-label="改正后的完整内容"
              className="min-h-48 resize-y"
              value={field.state.value}
              onChange={(e) => field.handleChange(e.target.value)}
            />
          )}
        </form.Field>
        <div className="flex justify-end gap-2">
          <Button variant="quiet" onClick={onCancel}>
            取消
          </Button>
          <form.Subscribe selector={(s) => s.isSubmitting}>
            {(busy) => (
              <Button type="submit" variant="primary" disabled={busy}>
                保存为新版本
              </Button>
            )}
          </form.Subscribe>
        </div>
      </Editor>
    </form>
  );
}

function ArchiveForm({ r, onDone, onCancel }: { r: MemoryRecord; onDone: () => void; onCancel: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);
  const form = useForm({
    defaultValues: { reason: "" },
    onSubmit: async ({ value }) => {
      if (!value.reason.trim()) {
        toast.error("请填写归档原因");
        input.current?.focus();
        return;
      }
      try {
        await api(`/memories/${enc(r.memory_id)}/archive`, { method: "POST", body: { reason: value.reason.trim() } });
        toast.success("已归档");
        onDone();
      } catch (error) {
        failed(error);
      }
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void form.handleSubmit();
      }}
    >
      <Editor hint="归档后这条记忆不再被检索到，版本历史保留。">
        <form.Field name="reason">
          {(field) => (
            <Input
              ref={input}
              aria-label="归档原因"
              placeholder="归档原因，例如：内容已过时"
              value={field.state.value}
              onChange={(e) => field.handleChange(e.target.value)}
            />
          )}
        </form.Field>
        <div className="flex justify-end gap-2">
          <Button variant="quiet" onClick={onCancel}>
            取消
          </Button>
          <form.Subscribe selector={(s) => s.isSubmitting}>
            {(busy) => (
              <Button type="submit" variant="primary" disabled={busy}>
                确认归档
              </Button>
            )}
          </form.Subscribe>
        </div>
      </Editor>
    </form>
  );
}

/**
 * `mode` is controlled so the docket's keyboard shortcuts can open an editor.
 * `onChanged(next)` gets the new version after a correction, or null after an archive.
 */
export function RecordCard({
  r,
  mode,
  onMode,
  onChanged,
  label,
}: {
  r: MemoryRecord;
  mode: EditMode;
  onMode: (mode: EditMode) => void;
  onChanged: (next: MemoryView | null) => void;
  label?: string;
}) {
  return (
    <section aria-label={label ?? r.entity_key} className="flex min-w-0 flex-1 flex-col rounded-[6px] border border-rule-strong bg-sheet">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-rule px-3.5 py-2.5">
        <span className="mr-auto font-mono text-[0.8125rem] leading-[1.4] font-medium [overflow-wrap:anywhere] text-ink">
          {r.entity_key}
        </span>
        <RecordStamps r={r} />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 px-3.5 pt-2 font-mono text-xs leading-normal text-ink-3 tabular-nums">
        <span>写入 {when(r.created_at)}</span>
        <span>生效 {when(r.valid_from)}</span>
        <span>版本 {r.versions.length}</span>
      </div>
      <div className="flex-1 px-3.5 pt-3 pb-4 leading-[1.7] [overflow-wrap:anywhere] whitespace-pre-wrap group-data-[single]/records:max-w-[80ch]">
        {r.content}
      </div>
      {r.archived_reason && <div className="px-3.5 pb-3 text-sm text-ink-2">归档原因：{r.archived_reason}</div>}
      {r.is_current && mode === "correct" && (
        <CorrectForm r={r} onCancel={() => onMode(null)} onDone={(next) => { onMode(null); onChanged(next); }} />
      )}
      {r.is_current && mode === "archive" && (
        <ArchiveForm r={r} onCancel={() => onMode(null)} onDone={() => { onMode(null); onChanged(null); }} />
      )}
      {r.is_current && !mode && (
        <div className="flex flex-wrap gap-2 border-t border-rule px-3.5 py-2.5">
          <Button onClick={() => onMode("correct")}>改正</Button>
          <Button variant="danger" onClick={() => onMode("archive")}>
            归档
          </Button>
        </div>
      )}
    </section>
  );
}

export function History({ r }: { r: MemoryRecord }) {
  return (
    <section className="mt-8">
      <h3 className="m-0 mb-2 text-sm font-semibold text-ink-2">版本历史（{r.versions.length}）</h3>
      <ol className="m-0 list-none border-t border-rule-strong p-0">
        {r.versions.map((v) => (
          <li key={v.memory_id} className="grid grid-cols-1 gap-x-4 gap-y-1 border-b border-rule py-3 md:grid-cols-[11rem_1fr]">
            <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs leading-[1.6] text-ink-3 tabular-nums md:grid md:content-start md:justify-items-start">
              <span>{when(v.created_at)}</span>
              <span className="flex flex-wrap gap-1">
                {v.is_current ? <Stamp tone="current">当前</Stamp> : <Stamp tone="archived">已失效</Stamp>}
                <Stamp tone={v.mutation_type === "correction" ? "correction" : "plain"}>
                  {MUTATION[v.mutation_type] ?? v.mutation_type}
                </Stamp>
                {v.conflict && <Stamp tone="conflict">冲突合并</Stamp>}
              </span>
            </div>
            <div>
              <div className={`text-sm [overflow-wrap:anywhere] whitespace-pre-wrap ${v.is_current ? "text-ink" : "text-ink-2"}`}>
                {v.content}
              </div>
              {v.archived_reason && <div className="mt-1 text-[0.8125rem] text-ink-3">归档原因：{v.archived_reason}</div>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
