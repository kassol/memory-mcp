// Maintenance (issue #16): start a round, follow it, and read the history of past rounds. The
// schedule belongs to the host cron; the page shows it, it cannot change it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Wrench } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, Loading, PageBody, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, failed } from "@/lib/api";
import { keys } from "@/lib/queries";
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

export function MaintenancePage() {
  const queryClient = useQueryClient();
  const rounds = useQuery({
    queryKey: keys.rounds,
    queryFn: () => api<{ items: MaintenanceRound[] }>("/overview/rounds").then((d) => d.items),
    refetchInterval: (query) => (query.state.data?.some((r) => r.status === "running") ? 3000 : false),
  });
  const overview = useQuery({ queryKey: keys.overview, queryFn: () => api<Overview>("/overview") });
  const [running, setRunning] = useState(false);

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

  return (
    <>
      <PageHeader title="维护" description="检查重复、矛盾与多版本，只产生发现，不自动改动记忆。">
        <Button variant="outline" size="sm" onClick={refresh}>
          刷新
        </Button>
      </PageHeader>
      <PageBody>
        <div className="flex flex-col gap-4">
          <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
            <CardHeader className="border-b border-border/70 px-5 py-4">
              <CardTitle className="text-[13px] font-medium">维护检查</CardTitle>
              <p className="text-xs text-muted-foreground">
                检查跨 key 重复、内部矛盾与同 key 多条当前版本。计划：{overview.data?.schedule ?? "由宿主机 cron 触发"}。
              </p>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-4 px-5 py-4">
              <Button onClick={() => void run()} disabled={running}>
                {running ? "已提交…" : "立即运行一轮"}
              </Button>
              <span className="text-xs text-muted-foreground">已有一轮在跑时会返回 409，等它结束再试。</span>
              {last ? (
                <span className="ml-auto flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className={`size-1.5 rounded-full ${STATUS[last.status]?.dot ?? "bg-muted-foreground/40"}`} />
                    上一轮 {STATUS[last.status]?.label ?? last.status}
                  </span>
                  <span className="tabular-nums">{when(last.finished_at ?? last.started_at)}</span>
                </span>
              ) : null}
            </CardContent>
          </Card>

          <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
            <CardHeader className="border-b border-border/70 px-5 py-4">
              <CardTitle className="text-[13px] font-medium">历史</CardTitle>
              <p className="text-xs text-muted-foreground">最近 20 轮，含调用次数、耗时与错误。</p>
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
                              {round.error ? <span title={round.error}>{round.error}</span> : null}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </PageBody>
    </>
  );
}
