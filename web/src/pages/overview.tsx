// Overview (issue #16): what needs attention, how memory moved, the last maintenance round,
// provider health, the stalest memories, token use, and 30-day charts.
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Inbox, KeyRound, Server, Wrench } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis } from "recharts";

import { ErrorState, Loading, PageBody, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import { KIND, when } from "@/lib/terms";
import type { DailyStat, Overview } from "@/lib/types";

const CHART = { writes: { label: "写入", color: "var(--chart-1)" }, recalls: { label: "召回", color: "var(--chart-2)" } } satisfies ChartConfig;
const LATENCY = { latency: { label: "耗时中位数", color: "var(--chart-3)" } } satisfies ChartConfig;

const KIND_DOT: Record<string, string> = {
  duplicate: "bg-primary",
  internal_contradiction: "bg-[var(--warning)]",
  multiple_current: "bg-muted-foreground/50",
  contradiction: "bg-[var(--warning)]",
};

interface Point {
  day: string;
  writes: number;
  recalls: number;
  latency: number | null;
}

/** Last 30 days, filled so the charts keep a steady x-axis; a day may have several tokens. */
function series(daily: DailyStat[]): Point[] {
  const buckets = new Map<string, { writes: number; recalls: number; weighted: number; weight: number }>();
  for (const stat of daily) {
    const bucket = buckets.get(stat.day) ?? { writes: 0, recalls: 0, weighted: 0, weight: 0 };
    bucket.writes += stat.writes;
    bucket.recalls += stat.recalls;
    if (stat.median_latency_ms !== null && stat.recalls > 0) {
      bucket.weighted += stat.median_latency_ms * stat.recalls;
      bucket.weight += stat.recalls;
    }
    buckets.set(stat.day, bucket);
  }
  const points: Point[] = [];
  for (let i = 29; i >= 0; i -= 1) {
    const day = new Date(Date.now() - i * 86_400_000).toISOString().slice(0, 10);
    const bucket = buckets.get(day);
    points.push({
      day,
      writes: bucket?.writes ?? 0,
      recalls: bucket?.recalls ?? 0,
      latency: bucket && bucket.weight ? Math.round((bucket.weighted / bucket.weight) * 10) / 10 : null,
    });
  }
  return points;
}

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="text-[19px] leading-none font-semibold tracking-[-0.02em] tabular-nums">{value}</span>
      {hint ? <span className="text-[11px] text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

function ChartBlock({
  title,
  value,
  children,
  first,
  last,
  legend,
  summary,
}: {
  title: string;
  value: string;
  children: React.ReactNode;
  first: string;
  last: string;
  legend?: React.ReactNode;
  summary?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-3 px-5 py-4 md:border-r md:border-border/70 md:last:border-r-0">
      {summary ? <p className="sr-only">{summary}</p> : null}
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-medium">{title}</h3>
          {legend}
        </div>
        <span className="text-[13px] font-medium tabular-nums">{value}</span>
      </div>
      {children}
      <div className="flex justify-between text-[10px] text-muted-foreground tabular-nums">
        <span>{first.slice(5)}</span>
        <span>{last.slice(5)}</span>
      </div>
    </div>
  );
}

export function OverviewPage() {
  const overview = useQuery({ queryKey: keys.overview, queryFn: () => api<Overview>("/overview") });

  const data = overview.data;
  const points = data ? series(data.daily) : [];
  const totalFindings = data?.findings.reduce((sum, f) => sum + f.count, 0) ?? 0;

  return (
    <>
      <PageHeader title="概览">
        <Button asChild variant="outline" size="sm">
          <Link to="/docket">
            去处理
            <ArrowRight />
          </Link>
        </Button>
      </PageHeader>
      <PageBody>
        {overview.error ? <ErrorState error={overview.error} onRetry={() => void overview.refetch()} /> : null}
        {!data && !overview.error ? <Loading rows={4} /> : null}
        {data ? (
          <div className="flex flex-col gap-4">
            <Card className="ring-0 border border-border/80 shadow-none">
              <CardContent className="grid gap-6 px-5 py-5 md:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] md:items-center">
                <div>
                  <div className="flex items-center gap-2 text-[13px] font-medium">
                    <Inbox className="size-4 text-primary" />
                    待审发现
                  </div>
                  <div className="mt-6 flex flex-wrap items-end gap-x-3 gap-y-1">
                    <span className="text-[46px] leading-[0.95] font-semibold tracking-[-0.04em] tabular-nums">{totalFindings}</span>
                    <span className="pb-1.5 text-sm text-muted-foreground">件待审</span>
                  </div>
                </div>
                <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2 md:border-l md:border-border/70 md:pl-8">
                  {data.findings.length ? (
                    data.findings.map((f) => (
                      <Link
                        key={f.kind}
                        to="/docket"
                        search={{ kind: f.kind }}
                        className="flex items-center gap-2 border-b border-border/60 py-2.5 text-sm transition-colors last:border-b-0 hover:text-primary"
                      >
                        <span className={`size-1.5 rounded-full ${KIND_DOT[f.kind] ?? "bg-muted-foreground/40"}`} />
                        <span>{KIND[f.kind] ?? f.kind}</span>
                        <span className="ml-auto text-[13px] font-medium tabular-nums">{f.count}</span>
                      </Link>
                    ))
                  ) : (
                    <span className="py-2 text-sm text-muted-foreground">没有待审发现。</span>
                  )}
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-4 sm:grid-cols-2">
              <Card className="ring-0 border border-border/80 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-[13px] font-medium">记忆</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-x-4 gap-y-4">
                  <Stat label="当前记忆" value={data.memories.total} />
                  <Stat label="7 天新增" value={data.memories.new_7d} hint={`30 天 ${data.memories.new_30d}`} />
                  <Stat label="7 天演化" value={data.memories.evolved_7d} hint={`30 天 ${data.memories.evolved_30d}`} />
                  <Stat
                    label="最久未更新"
                    value={data.stalest.length ? when(data.stalest[0].valid_from).slice(0, 10) : "—"}
                  />
                </CardContent>
              </Card>

              <Card className="ring-0 border border-border/80 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-[13px] font-medium">
                    <Wrench className="size-4 text-muted-foreground" />
                    维护
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">{data.schedule.split("（")[0]}</p>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  {data.last_round ? (
                    <>
                      <div className="flex items-center gap-2">
                        <span className={`flex items-center gap-1.5 text-[11px] ${data.last_round.status === "done" ? "text-[var(--success)]" : "text-destructive"}`}>
                          <span className={`size-1.5 rounded-full ${data.last_round.status === "done" ? "bg-[var(--success)]" : "bg-destructive"}`} />
                          {data.last_round.status === "done" ? "完成" : data.last_round.status === "running" ? "运行中" : "失败"}
                        </span>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {when(data.last_round.finished_at ?? data.last_round.started_at)}
                        </span>
                      </div>
                      <span className="text-sm">
                        模型调用 {String(data.last_round.stats.llm_calls ?? 0)} 次，发现{" "}
                        {Number(data.last_round.stats.duplicate ?? 0) + Number(data.last_round.stats.internal_contradiction ?? 0)}
                      </span>
                      {data.last_round.error ? (
                        <span className="text-xs break-all text-destructive">{data.last_round.error}</span>
                      ) : null}
                      <Button asChild variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground">
                        <Link to="/maintenance">查看历史</Link>
                      </Button>
                    </>
                  ) : (
                    <span className="text-sm text-muted-foreground">还没有运行过维护。</span>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card className="overflow-hidden ring-0 border border-border/80 shadow-none">
              <CardHeader className="pb-0">
                <CardTitle className="text-[13px] font-medium">近 30 天</CardTitle>
              </CardHeader>
              <CardContent className="grid px-0 md:grid-cols-2">
                <ChartBlock
                  title="写入与召回"
                  value={`写入 ${points.reduce((sum, p) => sum + p.writes, 0)} · 召回 ${points.reduce((sum, p) => sum + p.recalls, 0)}`}
                  first={points[0]?.day ?? ""}
                  last={points[points.length - 1]?.day ?? ""}
                  summary={`近 30 天写入 ${points.reduce((sum, p) => sum + p.writes, 0)} 次，召回 ${points.reduce((sum, p) => sum + p.recalls, 0)} 次。`}
                  legend={
                    <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1"><span className="size-1.5 rounded-[2px] bg-[var(--chart-1)]" />写入</span>
                      <span className="flex items-center gap-1"><span className="size-1.5 rounded-[2px] bg-[var(--chart-2)]" />召回</span>
                    </div>
                  }
                >
                  <ChartContainer config={CHART} className="h-28 w-full">
                    <BarChart data={points} barGap={2}>
                      <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.7} />
                      <XAxis dataKey="day" tick={false} tickLine={false} axisLine={false} />
                      <ChartTooltip content={<ChartTooltipContent labelKey="day" />} />
                      <Bar dataKey="writes" fill="var(--color-writes)" radius={2} isAnimationActive={false} />
                      <Bar dataKey="recalls" fill="var(--color-recalls)" radius={2} isAnimationActive={false} />
                    </BarChart>
                  </ChartContainer>
                </ChartBlock>
                <ChartBlock
                  title="召回耗时中位数"
                  value={(() => {
                    const latest = [...points].reverse().find((p) => p.latency !== null);
                    return latest?.latency == null ? "—" : `${latest.latency} ms`;
                  })()}
                  first={points[0]?.day ?? ""}
                  last={points[points.length - 1]?.day ?? ""}
                  summary={`最近一次召回耗时中位数 ${(() => {
                    const latest = [...points].reverse().find((p) => p.latency !== null);
                    return latest?.latency == null ? "暂无数据" : `${latest.latency} 毫秒`;
                  })()}。`}
                >
                  <ChartContainer config={LATENCY} className="h-28 w-full">
                    <LineChart data={points}>
                      <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.7} />
                      <XAxis dataKey="day" tick={false} tickLine={false} axisLine={false} />
                      <ChartTooltip content={<ChartTooltipContent labelKey="day" />} />
                      <Line dataKey="latency" stroke="var(--color-latency)" strokeWidth={1.6} dot={{ r: 1.8 }} connectNulls isAnimationActive={false} />
                    </LineChart>
                  </ChartContainer>
                </ChartBlock>
              </CardContent>
            </Card>

            <div className="grid gap-4 lg:grid-cols-3">
              <Card className="ring-0 border border-border/80 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-[13px] font-medium">
                    <Server className="size-4 text-muted-foreground" />
                    Provider
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {data.providers.map((p) => (
                    <div key={p.id} className="border-b border-border/60 pb-3 last:border-b-0 last:pb-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-xs break-all">{p.name}</span>
                        {p.last_call_ok === null ? (
                          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                            <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                            未调用
                          </span>
                        ) : (
                          <span className={`flex items-center gap-1.5 text-[11px] ${p.last_call_ok ? "text-[var(--success)]" : "text-destructive"}`}>
                            <span className={`size-1.5 rounded-full ${p.last_call_ok ? "bg-[var(--success)]" : "bg-destructive"}`} />
                            {p.last_call_ok ? "成功" : "失败"}
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] text-muted-foreground tabular-nums">{when(p.last_call_at)}</span>
                      {p.last_call_error ? (
                        <p className="line-clamp-2 text-[11px] break-all text-destructive" title={p.last_call_error}>
                          {p.last_call_error}
                        </p>
                      ) : null}
                    </div>
                  ))}
                  <Button asChild variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground">
                    <Link to="/settings" search={{ tab: "providers" }}>管理 Provider</Link>
                  </Button>
                </CardContent>
              </Card>

              <Card className="ring-0 border border-border/80 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-[13px] font-medium">最久未更新的记忆</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {data.stalest.length ? (
                    data.stalest.map((m) => (
                      <Link
                        key={m.memory_id}
                        to="/records"
                        search={{ memory: m.memory_id }}
                        className="group flex flex-col gap-1 border-b border-border/60 pb-3 last:border-b-0 last:pb-0"
                      >
                        <span className="font-mono text-[11px] break-all text-muted-foreground">{m.entity_key}</span>
                        <span className="line-clamp-1 text-[13px] transition-colors group-hover:text-primary">{m.content}</span>
                        <span className="text-[11px] text-muted-foreground tabular-nums">{when(m.valid_from)}</span>
                      </Link>
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground">还没有记忆。</span>
                  )}
                </CardContent>
              </Card>

              <Card className="ring-0 border border-border/80 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-[13px] font-medium">
                    <KeyRound className="size-4 text-muted-foreground" />
                    访问令牌
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {data.tokens.map((t) => (
                    <div key={t.name} className="border-b border-border/60 pb-3 last:border-b-0 last:pb-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-xs break-all">{t.name}</span>
                        {t.revoked_at ? (
                          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                            <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                            已吊销
                          </span>
                        ) : null}
                      </div>
                      <span className="text-[11px] text-muted-foreground tabular-nums">
                        {t.last_used_at ? when(t.last_used_at) : "从未使用"}
                      </span>
                    </div>
                  ))}
                  <Button asChild variant="ghost" size="sm" className="-ml-2 self-start text-muted-foreground">
                    <Link to="/settings" search={{ tab: "tokens" }}>管理令牌</Link>
                  </Button>
                </CardContent>
              </Card>
            </div>

            {data.memories.total === 0 ? (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <Inbox />
                  </EmptyMedia>
                  <EmptyTitle>还没有记忆</EmptyTitle>
                  <EmptyDescription>agent 通过 MCP 的 remember 写入后，这里会出现统计与图表。</EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : null}
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
