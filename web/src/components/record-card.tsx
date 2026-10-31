// One memory as a shadcn Card: full text, status badges, and inline correct / archive editors.
import { useForm } from "@tanstack/react-form";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, enc, failed } from "@/lib/api";
import { MUTATION, when } from "@/lib/terms";
import type { MemoryRecord, MemoryView } from "@/lib/types";

export type EditMode = "correct" | "archive" | null;

export function StatusBadges({ r }: { r: MemoryView }) {
  return (
    <>
      {r.is_current ? <Badge variant="secondary">当前</Badge> : <Badge variant="outline">已失效</Badge>}
      {r.mutation_type === "correction" && <Badge>改正</Badge>}
      {r.conflict && <Badge variant="outline">冲突合并</Badge>}
    </>
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
        const next = await api<MemoryView>(`/memories/${enc(r.memory_id)}/correct`, { method: "POST", body: { content: value.content } });
        toast.success("已保存改正版本");
        onDone(next);
      } catch (error) {
        failed(error);
      }
    },
  });
  return (
    <form
      className="w-full"
      onSubmit={(e) => {
        e.preventDefault();
        void form.handleSubmit();
      }}
    >
      <FieldGroup>
        <form.Field name="content">
          {(field) => (
            <Field>
              <FieldLabel htmlFor={`correct-${r.memory_id}`}>改正后的完整内容</FieldLabel>
              <Textarea
                ref={area}
                id={`correct-${r.memory_id}`}
                className="min-h-48"
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
              />
              <FieldDescription>保存后原文变为历史版本。这里写的内容原样替换，不经过自动合并。</FieldDescription>
            </Field>
          )}
        </form.Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onCancel}>
            取消
          </Button>
          <form.Subscribe selector={(s) => s.isSubmitting}>
            {(busy) => (
              <Button type="submit" disabled={busy}>
                保存为新版本
              </Button>
            )}
          </form.Subscribe>
        </div>
      </FieldGroup>
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
      className="w-full"
      onSubmit={(e) => {
        e.preventDefault();
        void form.handleSubmit();
      }}
    >
      <FieldGroup>
        <form.Field name="reason">
          {(field) => (
            <Field>
              <FieldLabel htmlFor={`archive-${r.memory_id}`}>归档原因</FieldLabel>
              <Input
                ref={input}
                id={`archive-${r.memory_id}`}
                placeholder="例如：内容已过时"
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
              />
              <FieldDescription>归档后这条记忆不再被检索到，版本历史保留。</FieldDescription>
            </Field>
          )}
        </form.Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onCancel}>
            取消
          </Button>
          <form.Subscribe selector={(s) => s.isSubmitting}>
            {(busy) => (
              <Button type="submit" variant="destructive" disabled={busy}>
                确认归档
              </Button>
            )}
          </form.Subscribe>
        </div>
      </FieldGroup>
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
    <Card role="region" aria-label={label ?? r.entity_key} className="min-w-0 flex-1">
      <CardHeader>
        <CardTitle className="font-mono text-sm break-all">{r.entity_key}</CardTitle>
        <CardDescription className="tabular-nums">
          写入 {when(r.created_at)} · 生效 {when(r.valid_from)} · 版本 {r.versions.length}
        </CardDescription>
        <CardAction className="flex flex-wrap justify-end gap-1">
          <StatusBadges r={r} />
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="leading-relaxed break-words whitespace-pre-wrap">{r.content}</p>
        {r.archived_reason && <p className="text-muted-foreground">归档原因：{r.archived_reason}</p>}
      </CardContent>
      {r.is_current && (
        <CardFooter className="border-t">
          {mode === "correct" && <CorrectForm r={r} onCancel={() => onMode(null)} onDone={(next) => { onMode(null); onChanged(next); }} />}
          {mode === "archive" && <ArchiveForm r={r} onCancel={() => onMode(null)} onDone={() => { onMode(null); onChanged(null); }} />}
          {!mode && (
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => onMode("correct")}>
                改正
              </Button>
              <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => onMode("archive")}>
                归档
              </Button>
            </div>
          )}
        </CardFooter>
      )}
    </Card>
  );
}

export function History({ r }: { r: MemoryRecord }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-sm font-medium">版本历史（{r.versions.length}）</h3>
      <ol className="flex flex-col gap-2">
        {r.versions.map((v) => (
          <li key={v.memory_id} className="rounded-lg border p-3">
            <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground tabular-nums">
              <span className="mr-1">{when(v.created_at)}</span>
              {v.is_current ? <Badge variant="secondary">当前</Badge> : <Badge variant="outline">已失效</Badge>}
              <Badge variant={v.mutation_type === "correction" ? "default" : "outline"}>{MUTATION[v.mutation_type] ?? v.mutation_type}</Badge>
              {v.conflict && <Badge variant="outline">冲突合并</Badge>}
            </div>
            <p className={`text-sm break-words whitespace-pre-wrap ${v.is_current ? "" : "text-muted-foreground"}`}>{v.content}</p>
            {v.archived_reason && <p className="mt-1 text-xs text-muted-foreground">归档原因：{v.archived_reason}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}
