// Page frame inside the sidebar inset: a quiet header, a centered body, and shared states.
import { AlertCircle, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <header className="flex min-h-16 shrink-0 items-center gap-3 border-b border-border/70 bg-background px-4 py-2.5 md:min-h-[68px] md:px-8 md:py-3">
      <SidebarTrigger className="-ml-1 shrink-0 text-muted-foreground hover:text-foreground" />
      <div className="min-w-0">
        <h1 className="truncate text-[22px] leading-tight font-semibold tracking-[-0.02em]">{title}</h1>
        {description ? <p className="mt-0.5 hidden truncate text-xs text-muted-foreground sm:block">{description}</p> : null}
      </div>
      {children ? <div className="ml-auto flex shrink-0 items-center gap-2">{children}</div> : null}
    </header>
  );
}

/** The scrolling body. Pages that build their own split layout opt out. */
export function PageBody({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("min-h-0 flex-1 overflow-y-auto", className)}>
      <div className="mx-auto w-full max-w-[1180px] px-4 py-6 md:px-8 md:py-8">{children}</div>
    </div>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="加载中">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-20 w-full rounded-xl" />
      ))}
    </div>
  );
}

/** The route-level fallback while a page chunk downloads. */
export function RouteLoading() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-16 items-center gap-3 border-b border-border/70 px-4 md:min-h-[68px] md:px-8">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="ml-auto h-7 w-20" />
      </div>
      <div className="mx-auto w-full max-w-[1180px] px-4 py-6 md:px-8 md:py-8">
        <Loading rows={3} />
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <Alert variant="destructive" className="border-destructive/25 bg-destructive/5">
      <AlertCircle />
      <AlertTitle>加载失败</AlertTitle>
      <AlertDescription>
        <p>{error.message}</p>
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            重试
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function EmptyState({ icon: Icon, title, children, action }: { icon: LucideIcon; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <Empty className="rounded-xl border border-dashed border-border/70 bg-card/40 py-12">
      <EmptyHeader>
        <EmptyMedia variant="icon" className="size-10 rounded-full bg-muted text-muted-foreground">
          <Icon />
        </EmptyMedia>
        <EmptyTitle className="text-sm font-medium">{title}</EmptyTitle>
        {children && <EmptyDescription className="text-xs">{children}</EmptyDescription>}
      </EmptyHeader>
      {action && <EmptyContent>{action}</EmptyContent>}
    </Empty>
  );
}
