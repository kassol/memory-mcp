// Docket: open findings, one case at a time, ruled by correct / archive / dismiss.
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight, Inbox } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, Loading, PageHeader } from "@/components/page";
import { RecordCard, type EditMode } from "@/components/record-card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsMobile } from "@/hooks/use-mobile";
import { api, enc, failed } from "@/lib/api";
import { keys, useFindings, useMemory } from "@/lib/queries";
import { caseNo, KIND } from "@/lib/terms";
import type { Finding, MemoryRecord, MemoryView } from "@/lib/types";
import { cn } from "@/lib/utils";

type Slot = 0 | 1;

const KIND_DOT: Record<string, string> = {
  duplicate: "bg-primary",
  internal_contradiction: "bg-[var(--warning)]",
  multiple_current: "bg-muted-foreground/50",
  contradiction: "bg-[var(--warning)]",
};

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

function SlotCard({ id, mode, onMode, onChanged, label }: {
  id: string;
  mode: EditMode;
  onMode: (m: EditMode) => void;
  onChanged: (next: MemoryView | null) => void;
  label: string;
}) {
  const memory = useMemory(id);
  if (memory.error) return <ErrorState error={memory.error} onRetry={() => void memory.refetch()} />;
  if (!memory.data) return <Skeleton className="h-56 w-full rounded-xl" />;
  return <RecordCard r={memory.data} label={label} mode={mode} onMode={onMode} onChanged={onChanged} />;
}

/** Exact-sentence comparison of a pair; the check opinion stays the authority for near matches. */
function PairSummary({ left, right }: { left: string; right: string }) {
  const a = useMemory(left);
  const b = useMemory(right);
  if (!a.data || !b.data) return null;
  const split = (text: string) => text.split(/(?<=[。！？；\n])/).map((s) => s.trim()).filter((s) => s.length >= 8);
  const onlyA = split(a.data.content);
  const onlyB = split(b.data.content);
  const setB = new Set(onlyB);
  const shared = onlyA.filter((s) => setB.has(s));
  const uniqueA = onlyA.filter((s) => !setB.has(s));
  const setA = new Set(onlyA);
  const uniqueB = onlyB.filter((s) => !setA.has(s));
  if (!shared.length && !uniqueA.length && !uniqueB.length) return null;

  const list = (items: string[]) => (
    <ul className="list-disc space-y-1 pl-4">
      {items.slice(0, 3).map((s) => <li key={s}>{s}</li>)}
      {items.length > 3 ? <li className="text-muted-foreground">还有 {items.length - 3} 句</li> : null}
    </ul>
  );

  return (
    <details className="rounded-lg border border-border/70 bg-card">
      <summary className="cursor-pointer px-3 py-2 text-[11px] text-muted-foreground select-none">
        对比摘要 · 共同 {shared.length} 句 · 仅甲 {uniqueA.length} · 仅乙 {uniqueB.length}
      </summary>
      <div className="grid gap-4 border-t border-border/60 px-3 py-3 text-[11px] leading-5 md:grid-cols-3">
        <div>
          <p className="mb-1.5 font-medium">共同</p>
          {shared.length ? list(shared) : <p className="text-muted-foreground">没有完全相同的句子。</p>}
        </div>
        <div>
          <p className="mb-1.5 font-medium">仅甲</p>
          {uniqueA.length ? list(uniqueA) : <p className="text-muted-foreground">无。</p>}
        </div>
        <div>
          <p className="mb-1.5 font-medium">仅乙</p>
          {uniqueB.length ? list(uniqueB) : <p className="text-muted-foreground">无。</p>}
        </div>
      </div>
    </details>
  );
}
function KeepActions({ left, right }: { left: string; right: string }) {
  const a = useMemory(left);
  const b = useMemory(right);
  const queryClient = useQueryClient();
  const [keeping, setKeeping] = useState<0 | 1 | null>(null);
  const [reason, setReason] = useState("与另一条内容重复，保留这一条");
  const [busy, setBusy] = useState(false);

  if (!a.data?.is_current || !b.data?.is_current) return null;
  const side = ["甲", "乙"];
  const other = (slot: 0 | 1) => (slot === 0 ? right : left);

  const archive = async () => {
    if (keeping === null) return;
    if (!reason.trim()) {
      toast.error("请填写归档原因");
      return;
    }
    setBusy(true);
    try {
      await api(`/memories/${enc(other(keeping))}/archive`, { method: "POST", body: { reason: reason.trim() } });
      void queryClient.invalidateQueries({ queryKey: keys.memory(other(keeping)) });
      toast.success(`已归档${side[keeping === 0 ? 1 : 0]}，下一次维护会关单`);
      setKeeping(null);
    } catch (error) {
      failed(error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/60 px-3 py-2.5">
        <span className="text-[11px] text-muted-foreground">其中一条只是重复：</span>
        <Button variant="outline" size="sm" onClick={() => setKeeping(0)}>保留甲，归档乙</Button>
        <Button variant="outline" size="sm" onClick={() => setKeeping(1)}>保留乙，归档甲</Button>
      </div>
      <Dialog open={keeping !== null} onOpenChange={(open) => !open && setKeeping(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>保留{keeping === 0 ? "甲" : "乙"}，归档{keeping === 0 ? "乙" : "甲"}？</DialogTitle>
            <DialogDescription>
              归档后另一条不再被检索到，版本历史保留。这件发现会在下一次维护时自动关闭。
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <label htmlFor="keep-reason" className="text-sm font-medium">归档原因</label>
            <Input id="keep-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setKeeping(null)}>取消</Button>
            <Button variant="destructive" disabled={busy} onClick={() => void archive()}>确认归档</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function Case({ finding, index, onDismissed, onBack, onMove, shift, position, total, hasPrev, hasNext }: {
  finding: Finding;
  index: number;
  onDismissed: () => void;
  onBack?: () => void;
  onMove: (step: 1 | -1) => void;
  shift: boolean;
  position: number;
  total: number;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  const queryClient = useQueryClient();
  // A correction replaces the card in place with the new version; an archive refetches the card,
  // which then shows as archived with its reason.
  const [ids, setIds] = useState(() => [finding.memory_id, finding.other_memory_id].filter((x): x is string => !!x));
  const [editing, setEditing] = useState<{ slot: Slot; mode: EditMode } | null>(null);
  const [dismissing, setDismissing] = useState(false);
  const pair = ids.length > 1;

  const dismiss = async () => {
    if (dismissing) return;
    setDismissing(true);
    try {
      await api(`/findings/${enc(finding.id)}/dismiss`, { method: "POST" });
      toast.success("已判为误报");
      onDismissed();
    } catch (error) {
      failed(error);
      setDismissing(false);
    }
  };

  const changed = (slot: Slot) => (next: MemoryView | null) => {
    if (next) setIds((prev) => prev.map((id, i) => (i === slot ? next.memory_id : id)));
    else void queryClient.invalidateQueries({ queryKey: keys.memory(ids[slot]) });
  };

  // J / K move between cases; C / A open correct or archive on the left record, with Shift on the
  // right one; D dismisses. Ignored while typing or while an editor or a dialog is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target) || editing || document.querySelector("[role=dialog]")) return;
      const key = e.key.toLowerCase();
      const slot: Slot = e.shiftKey && pair ? 1 : 0;
      if (key === "j") onMove(1);
      else if (key === "k") onMove(-1);
      else if (key === "d") void dismiss();
      else if (key === "c" || key === "a") {
        // Only a current record has editors; an archived one ignores C and A.
        const shown = queryClient.getQueryData<MemoryRecord>(keys.memory(ids[slot]));
        if (shown?.is_current) setEditing({ slot, mode: key === "c" ? "correct" : "archive" });
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const side = ["左侧", "右侧"];
  return (
    <div className="flex flex-col gap-5 px-4 py-6 md:px-8 md:py-8">
      {onBack && (
        <Button variant="ghost" size="sm" className="-ml-2 w-fit" onClick={onBack}>
          <ArrowLeft />
          返回列表
        </Button>
      )}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-[22px] leading-tight font-semibold tracking-[-0.02em]">卷宗 {caseNo(index)}</h2>
          <span className="flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
            <span className={`size-1.5 rounded-full ${KIND_DOT[finding.kind] ?? "bg-muted-foreground/40"}`} />
            {KIND[finding.kind] ?? finding.kind}
          </span>
          {finding.entity_key ? <span className="font-mono text-[11px] text-muted-foreground">{finding.entity_key}</span> : null}
          <span className="text-[11px] text-muted-foreground tabular-nums">队列 {position} / {total}</span>
          <span className="ml-auto flex items-center gap-1.5 text-[11px] text-muted-foreground">
            快捷键作用于
            <span className="rounded-md bg-card px-1.5 py-0.5 font-medium text-foreground ring-1 ring-border/70">
              {pair ? (shift ? "右侧 · 乙" : "左侧 · 甲") : "唯一记录"}
            </span>
          </span>
        </div>
        <p className="max-w-[62ch] text-[13px] leading-6 text-muted-foreground">
          {finding.detail ? (
            <>
              <span className="font-medium text-foreground">检查意见：</span>
              {finding.detail}
            </>
          ) : (
            "同一主题下有不止一条当前版本，保留正确的一条，归档其余。"
          )}
        </p>
      </div>
      <div className={cn("grid grid-cols-1 gap-4", pair && "xl:grid-cols-2")}>
        {ids.map((id, i) => (
          <SlotCard
            key={i}
            id={id}
            label={pair ? `${side[i]}记录` : "记录"}
            mode={editing?.slot === i ? editing.mode : null}
            onMode={(mode) => setEditing(mode ? { slot: i as Slot, mode } : null)}
            onChanged={changed(i as Slot)}
          />
        ))}
      </div>
      {pair ? <PairSummary left={ids[0]} right={ids[1]} /> : null}
      {pair ? <KeepActions left={ids[0]} right={ids[1]} /> : null}
      <div className="flex flex-wrap items-center gap-3 border-t border-border/70 pt-4">
        <p className="mr-auto text-xs text-muted-foreground">改正或归档任一条后，这件发现会在下一次维护时自动关闭。</p>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" disabled={!hasPrev} onClick={() => onMove(-1)}>
            <ChevronLeft />
            上一件
          </Button>
          <Button variant="outline" size="sm" disabled={!hasNext} onClick={() => onMove(1)}>
            下一件
            <ChevronRight />
          </Button>
        </div>
        <Button variant="outline" size="sm" disabled={dismissing} onClick={() => void dismiss()}>
          判为误报
        </Button>
      </div>
      <div className="hidden flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground md:flex" aria-label="快捷键">
        <span><Kbd>J</Kbd> <Kbd>K</Kbd> 下一件 / 上一件</span>
        <span><Kbd>C</Kbd> 改正</span>
        <span><Kbd>A</Kbd> 归档</span>
        {pair && <span><Kbd>⇧</Kbd> 加上一键作用于右侧</span>}
        <span><Kbd>D</Kbd> 判为误报</span>
      </div>
    </div>
  );
}

function CaseList({ items, selectedId, onOpen, indexOf }: { items: Finding[]; selectedId: string | null; onOpen: (id: string) => void; indexOf: (f: Finding) => number }) {
  return (
    <ul role="listbox" aria-label="待审的发现" className="flex min-w-0 flex-col gap-1 p-2">
      {items.map((f) => (
        <li key={f.id} role="option" aria-selected={f.id === selectedId}>
          <button
            type="button"
            onClick={() => onOpen(f.id)}
            onKeyDown={(e) => {
              if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
              e.preventDefault();
              const li = e.currentTarget.parentElement;
              const next = e.key === "ArrowDown" ? li?.nextElementSibling : li?.previousElementSibling;
              (next?.querySelector("button") as HTMLElement | null)?.focus();
            }}
            className={cn(
              "flex w-full min-w-0 flex-col gap-1.5 rounded-lg p-2.5 text-left text-sm transition-all",
              f.id === selectedId
                ? "bg-card shadow-[0_1px_2px_rgba(23,24,26,0.05),0_6px_18px_-14px_rgba(23,24,26,0.35)]"
                : "hover:bg-card/60",
            )}
          >
            <div className="flex w-full min-w-0 items-center gap-2">
              <span className="text-[11px] text-muted-foreground tabular-nums">{caseNo(indexOf(f))}</span>
              <span className={`size-1.5 rounded-full ${KIND_DOT[f.kind] ?? "bg-muted-foreground/40"}`} />
              <span className="text-[11px] text-muted-foreground">{KIND[f.kind] ?? f.kind}</span>
              <span className="ml-auto text-[10px] text-muted-foreground/80">{f.created_at.slice(5, 10)}</span>
            </div>
            <span className="w-full min-w-0 truncate font-mono text-[11px] text-muted-foreground">{f.entity_key ?? f.memory_id.slice(0, 8)}</span>
            <span className="line-clamp-2 w-full min-w-0 text-xs leading-5 break-all text-muted-foreground">{f.detail || f.entity_key || ""}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function DocketPage({ initialKind = null }: { initialKind?: string | null }) {
  const findings = useFindings();
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const [chosen, setChosen] = useState<string | null>(null);
  const [kind, setKind] = useState<string | null>(initialKind);
  const [shift, setShift] = useState(false);

  useEffect(() => {
    const down = (e: KeyboardEvent) => e.key === "Shift" && setShift(true);
    const up = (e: KeyboardEvent) => e.key === "Shift" && setShift(false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  const all = findings.data?.items ?? [];
  const counts = all.reduce<Record<string, number>>((acc, f) => {
    acc[f.kind] = (acc[f.kind] ?? 0) + 1;
    return acc;
  }, {});
  const items = kind ? all.filter((f) => f.kind === kind) : all;
  // Wide screens always show a case (the first by default); phones show the list until a case is opened.
  const selectedId = items.some((f) => f.id === chosen) ? chosen : isMobile ? null : (items[0]?.id ?? null);
  const index = items.findIndex((f) => f.id === selectedId);
  const globalIndex = all.findIndex((f) => f.id === selectedId);
  const reading = isMobile && index >= 0;

  const remove = (finding: Finding) => {
    const at = items.indexOf(finding);
    const rest = items.filter((f) => f.id !== finding.id);
    const remaining = all.filter((f) => f.id !== finding.id);
    queryClient.setQueryData(keys.findings, { items: remaining, total: remaining.length });
    const next = (kind ? rest : remaining)[Math.min(at, (kind ? rest : remaining).length - 1)];
    setChosen(next?.id ?? null);
  };

  const move = (step: 1 | -1) => {
    const next = items[index + step];
    if (next) setChosen(next.id);
  };

  return (
    <>
      <PageHeader title="待审" description="逐条判断，改正或归档后会在下一次维护自动关单。">
        {findings.data && <span className="hidden text-sm text-muted-foreground tabular-nums md:inline">{all.length} 件待审</span>}
      </PageHeader>
      {findings.isPending && <div className="p-4 md:p-8"><Loading /></div>}
      {findings.error && <div className="p-4 md:p-8"><ErrorState error={findings.error} onRetry={() => void findings.refetch()} /></div>}
      {findings.data && !all.length && (
        <div className="p-4 md:p-8">
          <EmptyState icon={Inbox} title="没有待审的发现">
            维护检查每天运行一次，新的发现会出现在这里。可以到「档案」里按最久未更新排序，检查陈旧记忆。
          </EmptyState>
        </div>
      )}
      {!!all.length && (
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[18rem_1fr]">
          <div className={cn("min-h-0 min-w-0 overflow-y-auto border-r border-border/70", reading && "hidden")}>
            <div className="sticky top-0 z-10 flex min-w-0 flex-col gap-2 border-b border-border/70 bg-background/95 px-3 py-3">
              <div className="flex items-baseline justify-between">
                <span className="text-xs font-medium">待审队列</span>
                <span className="text-[11px] text-muted-foreground tabular-nums">{items.length} / {all.length}</span>
              </div>
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={() => { setKind(null); setChosen(null); }}
                  className={cn("rounded-full px-2 py-1 text-[10px] transition-colors", kind === null ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted")}
                >
                  全部 {all.length}
                </button>
                {Object.entries(counts).map(([k, n]) => (
                  <button
                    key={k}
                    onClick={() => { setKind(k); setChosen(null); }}
                    className={cn("rounded-full px-2 py-1 text-[10px] transition-colors", kind === k ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted")}
                  >
                    {KIND[k] ?? k} {n}
                  </button>
                ))}
              </div>
            </div>
            <CaseList items={items} selectedId={selectedId} onOpen={setChosen} indexOf={(f) => all.findIndex((x) => x.id === f.id)} />
            {!items.length ? <p className="px-3 py-8 text-center text-xs text-muted-foreground">这一类没有待审发现。</p> : null}
          </div>
          {index >= 0 && (
            <div className="min-h-0 min-w-0 overflow-y-auto">
              <Case
                key={items[index].id}
                finding={items[index]}
                index={globalIndex >= 0 ? globalIndex : index}
                onDismissed={() => remove(items[index])}
                onBack={isMobile ? () => setChosen(null) : undefined}
                onMove={move}
                shift={shift}
                position={index + 1}
                total={items.length}
                hasPrev={index > 0}
                hasNext={index < items.length - 1}
              />
            </div>
          )}
        </div>
      )}
    </>
  );
}
