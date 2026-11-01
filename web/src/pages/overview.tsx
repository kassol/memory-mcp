// Overview (issue #16): one screen for what needs attention — open findings, how much memory moved,
// the last maintenance round, provider health, the stalest memories, token use, and 30-day charts.
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Gauge, Inbox, KeyRound, Server, Wrench } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis } from "recharts";

import { ErrorState, Loading, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import { KIND, when } from "@/lib/terms";
import type { DailyStat, Overview } from "@/lib/types";

const CHART = { writes: { label: "写入", color: "var(--chart-1)" }, recalls: { label: "召回", color: "var(--chart-2)" } } satisfies ChartConfig;
const LATENCY = { latency: { label: "耗时中位数", color: "var(--chart-3)" } } satisfies ChartConfig;

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
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-2xl font-medium tabular-nums">{value}</span>
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

export function OverviewPage() {
  const overview = useQuery({ queryKey: keys.overview, queryFn: () => api<Overview>("/overview") });

  if (overview.error) return <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />;
  const data = overview.data;
  const points = data ? series(data.daily) : [];

  return (
    <>
      <PageHeader title="概览" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 p-4 md:p-6">
          {!data ? (
            <Loading rows={4} />
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-3">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Inbox className="size-4" />
                      待审发现
                    </CardTitle>
                    <CardDescription>需要人判断的记忆问题。</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3">
                    {data.findings.length ? (
                      <>
                        {data.findings.map((f) => (
                          <div key={f.kind} className="flex items-center justify-between">
                            <Link to="/docket" className="text-sm hover:underline">
                              {KIND[f.kind] ?? f.kind}
                            </Link>
                            <span className="text-sm font-medium tabular-nums">{f.count}</span>
                          </div>
                        ))}
                        <Button asChild variant="outline" size="sm" className="mt-1 self-start">
                          <Link to="/docket">
                            去处理
                            <ArrowRight />
                          </Link>
                        </Button>
                      </>
                    ) : (
                      <span className="text-sm text-muted-foreground">没有待审发现。</span>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Gauge className="size-4" />
                      记忆
                    </CardTitle>
                    <CardDescription>当前版本总数，以及最近 7 / 30 天的变化。</CardDescription>
                  </CardHeader>
                  <CardContent className="grid grid-cols-2 gap-4">
                    <Stat label="当前记忆" value={data.memories.total} />
                    <Stat label="新增 7 天" value={data.memories.new_7d} hint={`30 天 ${data.memories.new_30d}`} />
                    <Stat label="演化 7 天" value={data.memories.evolved_7d} hint={`30 天 ${data.memories.evolved_30d}`} />
                    <Stat
                      label="最久未更新"
                      value={data.stalest.length ? when(data.stalest[0].valid_from).slice(0, 10) : "—"}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Wrench className="size-4" />
                      维护
                    </CardTitle>
                    <CardDescription>{data.schedule}</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    {data.last_round ? (
                      <>
                        <div className="flex items-center gap-2">
                          <Badge variant={data.last_round.status === "done" ? "secondary" : "destructive"}>
                            {data.last_round.status === "done" ? "完成" : data.last_round.status === "running" ? "运行中" : "失败"}
                          </Badge>
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
                        <Button asChild variant="outline" size="sm" className="self-start">
                          <Link to="/maintenance">查看历史</Link>
                        </Button>
                      </>
                    ) : (
                      <span className="text-sm text-muted-foreground">还没有运行过维护。</span>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">每日写入</CardTitle>
                    <CardDescription>30 天</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={CHART} className="h-32 w-full">
                      <BarChart data={points}>
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="day" tick={false} tickLine={false} axisLine={false} />
                        <ChartTooltip content={<ChartTooltipContent labelKey="day" />} />
                        <Bar dataKey="writes" fill="var(--color-writes)" radius={2} />
                      </BarChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">每日召回</CardTitle>
                    <CardDescription>30 天</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={CHART} className="h-32 w-full">
                      <BarChart data={points}>
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="day" tick={false} tickLine={false} axisLine={false} />
                        <ChartTooltip content={<ChartTooltipContent labelKey="day" />} />
                        <Bar dataKey="recalls" fill="var(--color-recalls)" radius={2} />
                      </BarChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">召回耗时中位数</CardTitle>
                    <CardDescription>毫秒，30 天</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={LATENCY} className="h-32 w-full">
                      <LineChart data={points}>
                        <CartesianGrid vertical={false} />
                        <XAxis dataKey="day" tick={false} tickLine={false} axisLine={false} />
                        <ChartTooltip content={<ChartTooltipContent labelKey="day" />} />
                        <Line dataKey="latency" stroke="var(--color-latency)" strokeWidth={2} dot={false} connectNulls />
                      </LineChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Server className="size-4" />
                      Provider
                    </CardTitle>
                    <CardDescription>最近一次调用的结果。</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3">
                    {data.providers.map((p, i) => (
                      <div key={p.id}>
                        {i > 0 && <Separator className="mb-3" />}
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-xs break-all">{p.name}</span>
                          {p.last_call_ok === null ? (
                            <Badge variant="outline">未调用</Badge>
                          ) : (
                            <Badge variant={p.last_call_ok ? "secondary" : "destructive"}>{p.last_call_ok ? "成功" : "失败"}</Badge>
                          )}
                        </div>
                        <span className="text-xs text-muted-foreground tabular-nums">{when(p.last_call_at)}</span>
                        {p.last_call_error ? (
                          <p className="line-clamp-2 text-xs break-all text-destructive" title={p.last_call_error}>
                            {p.last_call_error}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">最久未更新的记忆</CardTitle>
                    <CardDescription>按生效时间排序的前 5 条。</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3">
                    {data.stalest.length ? (
                      data.stalest.map((m) => (
                        <Link
                          key={m.memory_id}
                          to="/records"
                          search={{ memory: m.memory_id }}
                          className="flex flex-col gap-1 hover:underline"
                        >
                          <span className="font-mono text-xs break-all text-muted-foreground">{m.entity_key}</span>
                          <span className="line-clamp-1 text-sm">{m.content}</span>
                          <span className="text-xs text-muted-foreground tabular-nums">{when(m.valid_from)}</span>
                        </Link>
                      ))
                    ) : (
                      <span className="text-sm text-muted-foreground">还没有记忆。</span>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <KeyRound className="size-4" />
                      访问令牌
                    </CardTitle>
                    <CardDescription>最近使用时间。</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3">
                    {data.tokens.map((t, i) => (
                      <div key={t.name}>
                        {i > 0 && <Separator className="mb-3" />}
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-xs break-all">{t.name}</span>
                          {t.revoked_at ? <Badge variant="outline">已吊销</Badge> : null}
                        </div>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {t.last_used_at ? when(t.last_used_at) : "从未使用"}
                        </span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              {data.memories.total === 0 ? (
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <Gauge />
                    </EmptyMedia>
                    <EmptyTitle>还没有记忆</EmptyTitle>
                    <EmptyDescription>agent 通过 MCP 的 remember 写入后，这里会出现统计与图表。</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>
  );
}
