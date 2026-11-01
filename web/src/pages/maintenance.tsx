// Maintenance (issue #16): start a round, follow it, and read the history of past rounds. The
// schedule belongs to the host cron; the page shows it, it cannot change it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Wrench } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, Loading, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, failed } from "@/lib/api";
import { keys } from "@/lib/queries";
import { when } from "@/lib/terms";
import type { MaintenanceRound, Overview } from "@/lib/types";

const STATUS: Record<string, { label: string; variant: "secondary" | "destructive" | "outline" }> = {
  done: { label: "完成", variant: "secondary" },
  running: { label: "运行中", variant: "outline" },
  failed: { label: "失败", variant: "destructive" },
};

function Findings({ round }: { round: MaintenanceRound }) {
  const stats = round.stats;
  const found = Number(stats.duplicate ?? 0) + Number(stats.internal_contradiction ?? 0) + Number(stats.multiple_current ?? 0);
  return <span className="tabular-nums">{found}</span>;
}

export function MaintenancePage() {
  const queryClient = useQueryClient();
  const rounds = useQuery({ queryKey: keys.rounds, queryFn: () => api<{ items: MaintenanceRound[] }>("/overview/rounds").then((d) => d.items) });
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

  return (
    <>
      <PageHeader title="维护">
        <Button variant="outline" size="sm" onClick={refresh}>
          刷新
        </Button>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4 md:p-6">
          <Card>
            <CardHeader>
              <CardTitle>维护检查</CardTitle>
              <CardDescription>
                检查跨 key 重复、内部矛盾与同 key 多条当前版本，只产生发现，不自动归档或合并。计划：{overview.data?.schedule ?? "由宿主机 cron 触发"}。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void run()} disabled={running}>
                {running ? "已提交…" : "立即运行一轮"}
              </Button>
              <span className="text-sm text-muted-foreground">已有一轮在跑时会返回 409，等它结束再试。</span>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>历史</CardTitle>
              <CardDescription>最近 20 轮，含调用次数、耗时与错误。</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
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
                      <TableRow>
                        <TableHead>开始</TableHead>
                        <TableHead>状态</TableHead>
                        <TableHead className="text-right">耗时</TableHead>
                        <TableHead className="text-right">模型调用</TableHead>
                        <TableHead className="text-right">发现</TableHead>
                        <TableHead>错误</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rounds.data.map((round) => {
                        const status = STATUS[round.status] ?? { label: round.status, variant: "outline" as const };
                        return (
                          <TableRow key={round.id}>
                            <TableCell className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">
                              {when(round.started_at)}
                            </TableCell>
                            <TableCell>
                              <Badge variant={status.variant}>{status.label}</Badge>
                            </TableCell>
                            <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                              {round.duration_ms === null ? "—" : `${(round.duration_ms / 1000).toFixed(1)} s`}
                            </TableCell>
                            <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                              {String(round.stats.llm_calls ?? 0)}
                            </TableCell>
                            <TableCell className="text-right text-xs text-muted-foreground">
                              <Findings round={round} />
                            </TableCell>
                            <TableCell className="max-w-64 text-xs break-all text-destructive">{round.error ?? ""}</TableCell>
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
      </div>
    </>
  );
}
