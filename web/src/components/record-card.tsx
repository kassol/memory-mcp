// One memory as a quiet panel: full text, status badges, and inline correct / archive editors.
import { useForm } from "@tanstack/react-form";
import { ChevronDown, ClipboardCopy, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, enc, failed } from "@/lib/api";
import { diffSentences } from "@/lib/sentences";
import { MUTATION, when } from "@/lib/terms";
import type { MemoryRecord, MemoryView } from "@/lib/types";
import { cn } from "@/lib/utils";

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
        <CardDescription className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] tabular-nums">
          <span className="whitespace-nowrap">写入 {when(r.created_at)}</span>
          <span className="whitespace-nowrap">生效 {when(r.valid_from)}</span>
          <span className="whitespace-nowrap">版本 {r.versions.length}</span>
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

function ChangeList({ label, items, tone }: { label: string; items: string[]; tone: string }) {
  return (
    <div>
      <p className={cn("mb-1 font-medium", tone)}>{label}</p>
      {items.length ? (
        <ul className="list-disc space-y-1 pl-4">
          {items.map((sentence, index) => (
            <li key={`${index}-${sentence}`}>{sentence}</li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground">无。</p>
      )}
    </div>
  );
}

/** What the newer text changed, sentence by sentence. Collapsed until asked for. */
function VersionDiff({ older, newer }: { older: string | null; newer: string }) {
  if (!older) return <p className="text-[11px] text-muted-foreground">首个版本</p>;
  const diff = diffSentences(older, newer);
  if (!diff.added.length && !diff.removed.length) {
    return <p className="text-[11px] text-muted-foreground">内容没有变化</p>;
  }
  return (
    <details className="group rounded-lg border border-border/60 bg-muted/20">
      <summary className="flex cursor-pointer flex-wrap items-center gap-x-2 gap-y-1 px-2.5 py-1.5 text-[11px] text-muted-foreground select-none">
        <ChevronDown className="size-3 transition-transform group-open:rotate-90" />
        <span>相对上一版</span>
        {diff.added.length ? <span className="text-[var(--success)]">新增 {diff.added.length} 句</span> : null}
        {diff.removed.length ? <span className="text-destructive">删除 {diff.removed.length} 句</span> : null}
      </summary>
      <div className="grid gap-3 border-t border-border/60 px-2.5 py-2 text-[11px] leading-5 md:grid-cols-2">
        <ChangeList label="新增" items={diff.added} tone="text-[var(--success)]" />
        <ChangeList label="删除" items={diff.removed} tone="text-destructive" />
      </div>
    </details>
  );
}

/** Older versions are long; show three lines and let the reader open the rest. */
function VersionText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 240;
  return (
    <div className="flex flex-col gap-1">
      <p className={cn("text-[13px] leading-6 break-words whitespace-pre-wrap text-muted-foreground", long && !open && "line-clamp-3")}>
        {text}
      </p>
      {long ? (
        <Button
          variant="ghost"
          size="xs"
          className="-ml-2 w-fit text-[11px] text-muted-foreground"
          onClick={() => setOpen((value) => !value)}
        >
          <ChevronDown className={cn("transition-transform", open && "rotate-180")} />
          {open ? "收起" : "展开全文"}
        </Button>
      ) : null}
    </div>
  );
}

export function History({ r }: { r: MemoryRecord }) {
  const versions = r.versions;
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[13px] font-medium">版本历史（{versions.length}）</h3>
        {versions.length > 1 ? <span className="text-[11px] text-muted-foreground">当前版本见上</span> : null}
      </div>
      {versions.length <= 1 ? (
        <p className="text-xs text-muted-foreground">没有更早的版本。改正或演化后会在这里留下历史。</p>
      ) : (
        <ol className="relative flex flex-col gap-5 border-l border-border/80 pl-5">
          {versions.map((v, index) => {
            const older = versions[index + 1]?.content ?? null;
            return (
              <li key={v.memory_id} className="relative">
                <span className={`absolute top-1.5 -left-[25px] size-2 rounded-full ring-4 ring-background ${v.is_current ? "bg-primary" : "bg-border"}`} />
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground tabular-nums">
                  <span className="mr-1">{when(v.created_at)}</span>
                  {v.is_current ? <Badge variant="secondary">当前</Badge> : <Badge variant="outline">已失效</Badge>}
                  <Badge variant={v.mutation_type === "correction" ? "default" : "outline"}>{MUTATION[v.mutation_type] ?? v.mutation_type}</Badge>
                  {v.conflict && <Badge variant="outline">冲突合并</Badge>}
                </div>
                <div className="flex flex-col gap-2">
                  <VersionDiff older={older} newer={v.content} />
                  {v.is_current ? null : <VersionText text={v.content} />}
                  {v.archived_reason && <p className="text-xs text-muted-foreground">归档原因：{v.archived_reason}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
