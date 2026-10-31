// Docket: open findings, one case file at a time, ruled by correct / archive / dismiss.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CaseFile, EmptyRow, Ledger, Row, Rows, SkeletonRows, Workspace } from "@/components/ledger";
import { RecordCard, type EditMode } from "@/components/record-card";
import { Empty, ErrorNote, Skeleton, Stamp } from "@/components/registry";
import { Button } from "@/components/ui/button";
import { api, enc, failed } from "@/lib/api";
import { keys, useFindings, useMemory } from "@/lib/queries";
import { caseNo, KIND } from "@/lib/terms";
import type { Finding, MemoryView } from "@/lib/types";
import { useWide } from "@/lib/use-media";

type Slot = 0 | 1;

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

function Slot({ id, mode, onMode, onChanged, label }: {
  id: string;
  mode: EditMode;
  onMode: (m: EditMode) => void;
  onChanged: (next: MemoryView | null) => void;
  label: string;
}) {
  const memory = useMemory(id);
  if (memory.error) return <ErrorNote error={memory.error} onRetry={() => void memory.refetch()} />;
  if (!memory.data) {
    return (
      <div className="flex-1">
        <Skeleton />
        <Skeleton className="w-[60%]" />
      </div>
    );
  }
  return <RecordCard r={memory.data} label={label} mode={mode} onMode={onMode} onChanged={onChanged} />;
}

function Case({ finding, index, onDismissed, onBack, onMove }: {
  finding: Finding;
  index: number;
  onDismissed: () => void;
  onBack: () => void;
  onMove: (step: 1 | -1) => void;
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
      else if (key === "c" || key === "a") setEditing({ slot, mode: key === "c" ? "correct" : "archive" });
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const side = ["左侧", "右侧"];
  return (
    <CaseFile onBack={onBack}>
      <div className="mb-1 flex flex-wrap items-baseline gap-x-3 gap-y-2">
        <Stamp tone="kind">{KIND[finding.kind] ?? finding.kind}</Stamp>
        <h2 className="m-0 text-lg font-[650]">卷宗 {caseNo(index)}</h2>
      </div>
      <p className="mt-2 mb-5 max-w-[72ch] text-ink-2">
        {finding.detail ? (
          <>
            <b className="font-semibold text-ink">检查意见：</b>
            {finding.detail}
          </>
        ) : (
          "同一主题下有不止一条当前版本，保留正确的一条，归档其余。"
        )}
      </p>
      <div
        data-single={!pair || undefined}
        className={`group/records grid grid-cols-1 items-start gap-5 ${pair ? "xl:grid-cols-2" : ""}`}
      >
        {ids.map((id, i) => (
          <div key={i} className="flex min-w-0">
            <Slot
              id={id}
              label={pair ? `${side[i]}记录` : "记录"}
              mode={editing?.slot === i ? editing.mode : null}
              onMode={(mode) => setEditing(mode ? { slot: i as Slot, mode } : null)}
              onChanged={changed(i as Slot)}
            />
          </div>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-rule-strong pt-4">
        <span className="mr-auto text-[0.8125rem] text-ink-3">改正或归档任一条后，这件发现会在下一次维护时自动关闭。</span>
        <Button disabled={dismissing} onClick={() => void dismiss()}>
          判为误报
        </Button>
      </div>
      <p className="mt-4 hidden flex-wrap gap-x-3 gap-y-1 text-xs text-ink-3 md:flex" aria-label="快捷键">
        <span><kbd>J</kbd> <kbd>K</kbd> 下一件 / 上一件</span>
        <span><kbd>C</kbd> 改正</span>
        <span><kbd>A</kbd> 归档</span>
        {pair && <span><kbd>⇧</kbd> 加上一键作用于右侧</span>}
        <span><kbd>D</kbd> 判为误报</span>
      </p>
    </CaseFile>
  );
}

export function DocketPage() {
  const findings = useFindings();
  const queryClient = useQueryClient();
  const wide = useWide();
  const [chosen, setChosen] = useState<string | null>(null);
  const items = findings.data?.items ?? [];
  // Wide screens always show a case (the first by default); phones show the list until a row is opened.
  const selectedId = items.some((f) => f.id === chosen) ? chosen : wide ? (items[0]?.id ?? null) : null;
  const index = items.findIndex((f) => f.id === selectedId);

  const remove = (finding: Finding) => {
    const at = items.indexOf(finding);
    const rest = items.filter((f) => f.id !== finding.id);
    queryClient.setQueryData(keys.findings, { items: rest, total: rest.length });
    setChosen(rest[Math.min(at, rest.length - 1)]?.id ?? null);
  };

  const move = (step: 1 | -1) => {
    const next = items[index + step];
    if (next) setChosen(next.id);
  };

  return (
    <Workspace reading={selectedId !== null && (chosen !== null || wide)}>
      <Ledger
        label="待审列表"
        head={<div className="text-[0.8125rem] text-ink-3">待审的发现，按发现时间排列。逐条裁定：改正、归档或判为误报。</div>}
        foot={<span>{findings.data ? `${items.length} 件待审` : ""}</span>}
      >
        <Rows label="待审的发现">
          {findings.isPending && <SkeletonRows />}
          {findings.error && <li><ErrorNote error={findings.error} onRetry={() => void findings.refetch()} /></li>}
          {findings.data && !items.length && (
            <EmptyRow>
              <strong className="mb-1 block text-base text-ink">没有待审的发现</strong>
              维护检查每天运行一次，新的发现会出现在这里。
            </EmptyRow>
          )}
          {items.map((f, i) => (
            <Row
              key={f.id}
              no={caseNo(i)}
              rowKey={KIND[f.kind] ?? f.kind}
              gist={f.detail || f.entity_key || ""}
              selected={f.id === selectedId}
              onOpen={() => setChosen(f.id)}
            />
          ))}
        </Rows>
      </Ledger>
      {index >= 0 ? (
        <Case
          key={items[index].id}
          finding={items[index]}
          index={index}
          onDismissed={() => remove(items[index])}
          onBack={() => setChosen(null)}
          onMove={move}
        />
      ) : (
        findings.data &&
        !items.length && (
          <CaseFile>
            <Empty title="卷宗已清空">可以到「档案」里按最久未更新排序，检查陈旧记忆。</Empty>
          </CaseFile>
        )
      )}
    </Workspace>
  );
}
