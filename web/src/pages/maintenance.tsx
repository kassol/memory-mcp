// Maintenance (issue #16): start a round, follow it, and read the history of past rounds. The
// schedule belongs to the host cron; the page shows it, it cannot change it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, Loading, PageBody, PageHeader } from "@/components/page";
import { RefreshButton } from "@/components/refresh-button";
import { useIsMobile } from "@/hooks/use-mobile";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, failed } from "@/lib/api";
import { keys, useSettings } from "@/lib/queries";
import { when } from "@/lib/terms";
import type { MaintenanceRound, Overview } from "@/lib/types";

const STATUS: Record<string, { label: string; dot: string }> = {
  done: { label: "完成", dot: "bg-[var(--success)]" },
  running: { label: "运行中", dot: "bg-[var(--warning)]" },
  failed: { label: "失败", dot: "bg-destructive" },
};

function Findings({ round }: { round: MaintenanceRound }) {
  const stats = round.stats;
  const found = Number(stats.duplicate ?? 0) + Number(stats.internal_contradiction ?? 0) + Number(stats.multiple_current ?? 0);
  return <span className="tabular-nums">{found}</span>;
}

/** Turn backend error prose into a short line; the raw text stays behind 详情. */
function errorSummary(error: string): string {
  const failed = error.match(/^(\d+)\s+judgment\(s\) failed/i);
  if (failed) return `本轮有 ${failed[1]} 项判定失败`;
  const first = error.split("\n")[0];
  return first.length > 80 ? `${first.slice(0, 80)}…` : first;
}

export function MaintenancePage() {
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const rounds = useQuery({
    queryKey: keys.rounds,
    queryFn: () => api<{ items: MaintenanceRound[] }>("/overview/rounds").then((d) => d.items),
    refetchInterval: (query) => (query.state.data?.some((r) => r.status === "running") ? 3000 : false),
  });
  const overview = useQuery({ queryKey: keys.overview, queryFn: () => api<Overview>("/overview") });
  const settings = useSettings();
  const budget = settings.data?.find((s) => s.key === "maintenance_max_llm_calls")?.value;
  const [running, setRunning] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: keys.rounds });
    void queryClient.invalidateQueries({ queryKey: keys.overview });
  };

  const run = async () => {
    setRunning(true);
    try {
      await api<{ job_id: string }>("/maintenance/run", { method: "POST" });
      toast.success("已开始一轮维护");
      refresh();
    } catch (error) {
      failed(error);
    } finally {
      setRunning(false);
    }
  };

  const last = overview.data?.last_round;
  const runningRound = rounds.data?.find((r) => r.status === "running") ?? null;
  const isRunning = runningRound !== null;

  useEffect(() => {
    if (!isRunning) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isRunning]);

  const elapsed = runningRound?.started_at
    ? Math.max(0, Math.floor((now - new Date(runningRound.started_at).getTime()) / 1000))
    : null;
  const elapsedLabel = elapsed === null ? null : elapsed < 60 ? `${elapsed} 秒` : `${Math.floor(elapsed / 60)} 分 ${elapsed % 60} 秒`;

  return (
    <>
      <PageHeader title="维护">
        <RefreshButton label="刷新维护" busy={rounds.isFetching || overview.isFetching} onClick={refresh} />
      </PageHeader>
      <PageBody>
        <div className="flex flex-col gap-4">
          <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
            <CardHeader className="border-b border-border/70 px-5 py-4">
              <CardTitle className="text-[13px] font-medium">维护检查</CardTitle>
              <p className="text-xs text-muted-foreground">计划：{overview.data?.schedule ?? "由宿主机 cron 触发"}</p>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-4 px-5 py-4">
              <Button onClick={() => void run()} disabled={running || isRunning}>
                {running ? "已提交…" : isRunning ? "运行中…" : "立即运行一轮"}
              </Button>
              {last ? (
                <span className="ml-auto flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className={`size-1.5 rounded-full ${STATUS[last.status]?.dot ?? "bg-muted-foreground/40"}`} />
                    上一轮 {STATUS[last.status]?.label ?? last.status}
                  </span>
                  {elapsedLabel ? <span className="tabular-nums">已运行 {elapsedLabel}</span> : null}
                  {!elapsedLabel ? <span className="tabular-nums">{when(last.finished_at ?? last.started_at)}</span> : null}
                </span>
              ) : null}
              {typeof budget === "number" ? (
                <p className="w-full text-[11px] text-muted-foreground">单轮最多 {budget} 次模型调用；没跑完的留到下一轮。</p>
              ) : null}
            </CardContent>
          </Card>

          <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
            <CardHeader className="border-b border-border/70 px-5 py-4">
              <CardTitle className="text-[13px] font-medium">历史</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 px-5 py-4">
              {rounds.error && <ErrorState error={rounds.error} onRetry={() => void rounds.refetch()} />}
              {rounds.isPending && <Loading rows={3} />}
              {rounds.data && !rounds.data.length ? (
                <EmptyState icon={Wrench} title="还没有运行过维护">
                  宿主机 cron 每天触发一次，也可以用上面的按钮立即跑一轮。
                </EmptyState>
              ) : null}
              {rounds.data && rounds.data.length ? (
                isMobile ? (
                  <div className="flex flex-col gap-2">
                    {rounds.data.map((round) => {
                      const status = STATUS[round.status] ?? { label: round.status, dot: "bg-muted-foreground/40" };
                      return (
                        <div key={round.id} className="rounded-xl border border-border/80 bg-card p-3.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[11px] text-muted-foreground tabular-nums">{when(round.started_at)}</span>
                            <span className="flex items-center gap-1.5 text-[11px]">
                              <span className={`size-1.5 rounded-full ${status.dot}`} />
                              {status.label}
                            </span>
                          </div>
                          <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-muted-foreground">
                            <span>耗时 <b className="font-medium text-foreground tabular-nums">{round.duration_ms === null ? "—" : `${(round.duration_ms / 1000).toFixed(1)} s`}</b></span>
                            <span>调用 <b className="font-medium text-foreground tabular-nums">{String(round.stats.llm_calls ?? 0)}</b></span>
                            <span>发现 <b className="font-medium text-foreground tabular-nums"><Findings round={round} /></b></span>
                          </div>
                          {round.error ? (
                            <details className="group mt-2 border-t border-border/60 pt-2 text-[11px]">
                              <summary className="flex cursor-pointer items-center gap-1 text-destructive">
                                <ChevronRight className="size-3 transition-transform group-open:rotate-90" />
                                {errorSummary(round.error)}
                              </summary>
                              <p className="mt-1 whitespace-pre-wrap break-all text-muted-foreground">{round.error}</p>
                            </details>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border/70 hover:bg-transparent">
                        <TableHead className="h-9 px-3 text-[11px] font-medium text-muted-foreground">开始</TableHead>
                        <TableHead className="h-9 px-3 text-[11px] font-medium text-muted-foreground">状态</TableHead>
                        <TableHead className="h-9 w-24 px-3 text-right text-[11px] font-medium text-muted-foreground">耗时</TableHead>
                        <TableHead className="h-9 px-3 text-right text-[11px] font-medium text-muted-foreground">模型调用</TableHead>
                        <TableHead className="h-9 px-3 text-right text-[11px] font-medium text-muted-foreground">发现</TableHead>
                        <TableHead className="h-9 px-3 text-[11px] font-medium text-muted-foreground">错误</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rounds.data.map((round) => {
                        const status = STATUS[round.status] ?? { label: round.status, dot: "bg-muted-foreground/40" };
                        return (
                          <TableRow key={round.id} className="border-border/60">
                            <TableCell className="px-3 py-2.5 text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">
                              {when(round.started_at)}
                            </TableCell>
                            <TableCell className="px-3 py-2.5">
                              <span className="flex items-center gap-1.5 text-[11px]">
                                <span className={`size-1.5 rounded-full ${status.dot}`} />
                                {status.label}
                              </span>
                            </TableCell>
                            <TableCell className="w-24 px-3 py-2.5 text-right text-[11px] text-muted-foreground tabular-nums">
                              {round.duration_ms === null ? "—" : `${(round.duration_ms / 1000).toFixed(1)} s`}
                            </TableCell>
                            <TableCell className="px-3 py-2.5 text-right text-[11px] text-muted-foreground tabular-nums">
                              {String(round.stats.llm_calls ?? 0)}
                            </TableCell>
                            <TableCell className="px-3 py-2.5 text-right text-[11px] text-muted-foreground">
                              <Findings round={round} />
                            </TableCell>
                            <TableCell className="max-w-64 px-3 py-2.5 text-[11px] break-all text-destructive" style={{ whiteSpace: "normal" }}>
                              {round.error ? (
                                <div className="flex flex-col gap-1">
                                  <span title={round.error}>{errorSummary(round.error)}</span>
                                  {errorSummary(round.error) !== round.error ? (
                                    <details className="group">
                                      <summary className="flex cursor-pointer items-center gap-1 text-[10px] text-muted-foreground">
                                        <ChevronRight className="size-3 transition-transform group-open:rotate-90" />
                                        详情
                                      </summary>
                                      <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{round.error}</p>
                                    </details>
                                  ) : null}
                                </div>
                              ) : null}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
                )
              ) : null}
            </CardContent>
          </Card>
        </div>
      </PageBody>
    </>
  );
}
