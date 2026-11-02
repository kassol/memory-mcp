// One memory as a quiet panel: full text, status badges, and inline correct / archive editors.
import { useForm } from "@tanstack/react-form";
import { ClipboardCopy, Copy } from "lucide-react";
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
      {r.is_current ? (
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="size-1.5 rounded-full bg-[var(--success)]" />
          当前
        </span>
      ) : (
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="size-1.5 rounded-full bg-muted-foreground/40" />
          已失效
        </span>
      )}
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
                className="min-h-48 text-[13px] leading-6"
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
  const mark = label?.startsWith("左侧") ? "甲" : label?.startsWith("右侧") ? "乙" : null;
  const copy = (value: string, message: string) => {
    void navigator.clipboard.writeText(value).then(
      () => toast.success(message),
      () => toast.error("复制失败，请手动选中"),
    );
  };
  return (
    <Card role="region" aria-label={label ?? r.entity_key} className="min-w-0 flex-1 h-full gap-4 self-stretch rounded-xl border border-border/80 shadow-none ring-0">
      <CardHeader className="gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {mark ? (
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
              {mark}
            </span>
          ) : null}
          <CardTitle className="min-w-0 truncate font-mono text-[12px] font-medium text-muted-foreground">{r.entity_key}</CardTitle>
          <Button
            variant="ghost"
            size="icon-xs"
            className="shrink-0 text-muted-foreground"
            aria-label="复制 key"
            onClick={() => copy(r.entity_key, "已复制 key")}
          >
            <Copy />
          </Button>
        </div>
        <CardDescription className="text-[11px] tabular-nums">
          写入 {when(r.created_at)} · 生效 {when(r.valid_from)} · 版本 {r.versions.length}
        </CardDescription>
        <CardAction className="flex flex-wrap items-center justify-end gap-1">
          <Button
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground"
            aria-label="复制全文"
            title="复制全文"
            onClick={() => copy(r.content, "已复制全文")}
          >
            <ClipboardCopy />
          </Button>
          <StatusBadges r={r} />
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <p className="text-[13.5px] leading-7 break-words whitespace-pre-wrap">{r.content}</p>
        {r.archived_reason && <p className="text-xs text-muted-foreground">归档原因：{r.archived_reason}</p>}
      </CardContent>
      {r.is_current && (
        <CardFooter className="mt-auto border-t border-border/70 bg-transparent">
          {mode === "correct" && <CorrectForm r={r} onCancel={() => onMode(null)} onDone={(next) => { onMode(null); onChanged(next); }} />}
          {mode === "archive" && <ArchiveForm r={r} onCancel={() => onMode(null)} onDone={() => { onMode(null); onChanged(null); }} />}
          {!mode && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => onMode("correct")}>
                改正
              </Button>
              <Button variant="ghost" size="sm" className="text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => onMode("archive")}>
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
    <section className="flex flex-col gap-4">
      <h3 className="text-[13px] font-medium">版本历史（{r.versions.length}）</h3>
      <ol className="relative flex flex-col gap-4 border-l border-border/80 pl-5">
        {r.versions.map((v) => (
          <li key={v.memory_id} className="relative">
            <span className={`absolute top-1.5 -left-[25px] size-2 rounded-full ring-4 ring-background ${v.is_current ? "bg-primary" : "bg-border"}`} />
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground tabular-nums">
              <span className="mr-1">{when(v.created_at)}</span>
              {v.is_current ? <Badge variant="secondary">当前</Badge> : <Badge variant="outline">已失效</Badge>}
              <Badge variant={v.mutation_type === "correction" ? "default" : "outline"}>{MUTATION[v.mutation_type] ?? v.mutation_type}</Badge>
              {v.conflict && <Badge variant="outline">冲突合并</Badge>}
            </div>
            <p className={`text-[13px] leading-6 break-words whitespace-pre-wrap ${v.is_current ? "" : "text-muted-foreground"}`}>{v.content}</p>
            {v.archived_reason && <p className="mt-1 text-xs text-muted-foreground">归档原因：{v.archived_reason}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}
