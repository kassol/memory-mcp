// Registry building blocks shared by the docket and the records pages (DESIGN.md signature components).
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type StampTone = "current" | "archived" | "correction" | "conflict" | "kind" | "plain";

const TONE: Record<StampTone, string> = {
  current: "text-ok",
  archived: "text-ink-3",
  correction: "text-blue",
  conflict: "text-warn",
  kind: "text-warn",
  plain: "text-ink-2",
};

/** An outlined status mark in currentColor; never filled. */
export function Stamp({ tone = "plain", children }: { tone?: StampTone; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-block rounded-[3px] border border-current px-[0.4375rem] py-1 text-[0.6875rem] leading-none font-semibold tracking-[0.04em] whitespace-nowrap",
        TONE[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("my-2 h-3 rounded-[3px] bg-rule motion-safe:animate-pulse", className)} />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-5 py-10 text-ink-2">
      <strong className="mb-1 block text-base text-ink">{title}</strong>
      {children}
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="px-5 py-10 text-ink-2">
      <strong className="mb-1 block text-base text-danger">加载失败</strong>
      <p className="m-0 mb-3">{error.message}</p>
      {onRetry && (
        <button type="button" className="text-ink-2 underline underline-offset-3 hover:text-ink" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
}
