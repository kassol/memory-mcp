// Ledger column + case file: the two-column workspace of the docket and the records pages.
// Rows form a listbox: Enter or Space opens a row, Up and Down move between rows.
import { ArrowLeft } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";

import { Skeleton } from "@/components/registry";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Workspace({ reading, children }: { reading: boolean; children: ReactNode }) {
  return (
    <div
      data-reading={reading || undefined}
      className="group/ws grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(18rem,26rem)_1fr]"
    >
      {children}
    </div>
  );
}

export function Ledger({ label, head, foot, children }: { label: string; head: ReactNode; foot: ReactNode; children: ReactNode }) {
  return (
    <aside
      aria-label={label}
      className="flex min-h-0 flex-col bg-sheet group-data-[reading]/ws:max-md:hidden md:border-r md:border-rule-strong"
    >
      <div className="grid gap-2 border-b border-rule px-4 py-3">{head}</div>
      {children}
      <div className="flex items-center justify-between border-t border-rule px-4 py-2 text-[0.8125rem] text-ink-3">{foot}</div>
    </aside>
  );
}

export function Rows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ol role="listbox" aria-label={label} className="m-0 min-h-0 flex-1 list-none overflow-y-auto p-0">
      {children}
    </ol>
  );
}

export function SkeletonRows() {
  return Array.from({ length: 6 }, (_, i) => (
    <li key={i} aria-hidden className="grid grid-cols-[auto_1fr] gap-x-3 border-b border-rule px-4 py-2.5">
      <span className="min-w-[2.5ch]" />
      <div>
        <Skeleton />
        <Skeleton className="w-[70%]" />
      </div>
    </li>
  ));
}

function moveFocus(event: KeyboardEvent<HTMLLIElement>) {
  const next = event.key === "ArrowDown" ? event.currentTarget.nextElementSibling : event.currentTarget.previousElementSibling;
  (next as HTMLElement | null)?.focus();
}

export function Row({
  no,
  rowKey,
  identifier,
  gist,
  selected,
  onOpen,
}: {
  no: string;
  rowKey: ReactNode;
  identifier?: boolean;
  gist: string;
  selected: boolean;
  onOpen: () => void;
}) {
  return (
    <li
      role="option"
      aria-selected={selected}
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          moveFocus(e);
        }
      }}
      className={cn(
        "relative grid cursor-pointer grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 border-b border-rule px-4 py-2.5 hover:bg-ground",
        "aria-selected:bg-wash aria-selected:before:absolute aria-selected:before:inset-y-0 aria-selected:before:left-0 aria-selected:before:w-0.5 aria-selected:before:bg-blue",
      )}
    >
      <span className="row-span-2 min-w-[2.5ch] pt-px text-right font-mono text-xs leading-[1.6] font-medium text-ink-3 tabular-nums">
        {no}
      </span>
      <span
        className={cn(
          "truncate text-[0.8125rem] leading-normal font-medium text-ink-2",
          identifier && "font-mono",
        )}
      >
        {rowKey}
      </span>
      <span className="line-clamp-2 text-sm text-ink">{gist}</span>
    </li>
  );
}

export function EmptyRow({ children }: { children: ReactNode }) {
  return (
    <li role="option" aria-selected={false} aria-disabled className="px-5 py-10 text-ink-2">
      {children}
    </li>
  );
}

export function CaseFile({ children, onBack }: { children: ReactNode; onBack?: () => void }) {
  return (
    <article
      aria-live="polite"
      className="min-w-0 overflow-y-auto px-4 pt-4 pb-12 group-data-[reading]/ws:max-md:block max-md:hidden md:px-8 md:pt-6"
    >
      {onBack && (
        <Button variant="quiet" className="-ml-2 mb-3 md:hidden" onClick={onBack}>
          <ArrowLeft aria-hidden />
          返回列表
        </Button>
      )}
      {children}
    </article>
  );
}
