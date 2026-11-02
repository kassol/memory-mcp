// Startup settings (issue #14): read before the service starts, so a change is a draft, a check and
// an apply that restarts the process. The page then polls /health until the service is back.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorState, Loading } from "@/components/page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api, failed } from "@/lib/api";
import { keys, useStartupSettings } from "@/lib/queries";
import { when } from "@/lib/terms";
import type { StartupSettings } from "@/lib/types";

const BACKENDS = [
  { value: "lancedb", label: "lancedb" },
  { value: "memory", label: "memory（进程内，重启后丢失）" },
  { value: "auto", label: "auto（lancedb 不可用时退回 memory）" },
];

const APPLY_STATUS: Record<string, string> = { pending: "重启中", applied: "已生效", failed: "已回退" };

interface Values {
  port: string;
  data_dir: string;
  vector_backend: string;
  debug: boolean;
}

function initial(s: StartupSettings): Values {
  const pick = (key: string) => (key in s.draft ? s.draft[key] : s.effective[key]);
  return {
    port: String(pick("port") ?? ""),
    data_dir: String(pick("data_dir") ?? ""),
    vector_backend: String(pick("vector_backend") ?? "lancedb"),
    debug: Boolean(pick("debug")),
  };
}

function pendingKeys(s: StartupSettings, values: Values): Record<string, string | number | boolean> {
  const body: Record<string, string | number | boolean> = {};
  if (s.editable.includes("port") && Number(values.port) !== Number(s.effective.port)) body.port = Number(values.port);
  if (s.editable.includes("data_dir") && values.data_dir !== String(s.effective.data_dir)) body.data_dir = values.data_dir;
  if (s.editable.includes("vector_backend") && values.vector_backend !== String(s.effective.vector_backend)) {
    body.vector_backend = values.vector_backend;
  }
  if (s.editable.includes("debug") && values.debug !== Boolean(s.effective.debug)) body.debug = values.debug;
  return body;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** One health probe, bounded: during a restart a request can hang instead of failing. */
async function healthy(): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const res = await fetch("/health", { cache: "no-store", signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * The old process answers /health until it exits, so "healthy" right after apply means nothing:
 * wait for it to go away first, then for the service to be back.
 */
async function waitForRestart(): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < 15_000) {
    if (!(await healthy())) break;
    await sleep(300);
  }
  while (Date.now() - started < 120_000) {
    if (await healthy()) return;
    await sleep(1500);
  }
  throw new Error("服务在 120 秒内没有恢复");
}

/** The reload itself can land while the proxy still returns 502 to the new process. */
async function retry<T>(run: () => Promise<T>, attempts = 8): Promise<T> {
  let last: unknown;
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await run();
    } catch (error) {
      last = error;
      await sleep(1500);
    }
  }
  throw last instanceof Error ? last : new Error(String(last));
}

export function StartupSection() {
  const queryClient = useQueryClient();
  const startup = useStartupSettings();
  const [values, setValues] = useState<Values | null>(null);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [restarting, setRestarting] = useState(false);

  if (startup.error) return <ErrorState error={startup.error} onRetry={() => void startup.refetch()} />;
  if (!startup.data) return <Loading rows={3} />;

  const data = startup.data;
  const current = values ?? initial(data);
  const changed = pendingKeys(data, current);
  const set = (patch: Partial<Values>) => setValues({ ...current, ...patch });
  const store = (next: StartupSettings) => {
    queryClient.setQueryData(keys.startup, next);
    setValues(initial(next));
  };

  const saveDraft = async () => {
    setProblems(null);
    if (!Object.keys(changed).length) {
      toast.success("没有改动");
      return;
    }
    try {
      store(await api<StartupSettings>("/startup-settings", { method: "PUT", body: changed }));
      toast.success("已保存为待生效");
    } catch (error) {
      failed(error);
    }
  };

  const check = async () => {
    try {
      const result = await api<{ ok: boolean; problems: string[] }>("/startup-settings/check", { method: "POST" });
      setProblems(result.problems);
      if (result.ok) toast.success("校验通过");
    } catch (error) {
      failed(error);
    }
  };

  const discard = async () => {
    try {
      store(await api<StartupSettings>("/startup-settings", { method: "DELETE" }));
      setProblems(null);
      toast.success("已丢弃待生效的设置");
    } catch (error) {
      failed(error);
    }
  };

  const apply = async () => {
    setRestarting(true);
    setProblems(null);
    try {
      await api<{ applying: boolean }>("/startup-settings/apply", { method: "POST" });
      await waitForRestart();
      store(await retry(() => api<StartupSettings>("/startup-settings")));
      toast.success("服务已用新设置重启");
    } catch (error) {
      failed(error);
    } finally {
      setRestarting(false);
    }
  };

  return (
    <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/70 px-5 py-4">
        <CardTitle className="text-[13px] font-medium">启动设置</CardTitle>
        <CardDescription className="text-xs">
          只在服务启动时读取，改动要校验、再应用。应用会让进程退出并由重启策略拉起；起不来时回退到上一份设置并记下原因。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 px-5 py-4">
        {data.container ? (
          <Alert>
            <AlertTitle>容器里运行</AlertTitle>
            <AlertDescription>端口与数据目录由容器编排决定，在这里只读。其余设置可以改，应用后自动重启。</AlertDescription>
          </Alert>
        ) : (
          <Alert>
            <AlertTitle>手工运行</AlertTitle>
            <AlertDescription>应用后进程会退出。没有容器重启策略或进程守护时，需要手动再启动一次。</AlertDescription>
          </Alert>
        )}

        <div className="grid gap-5 md:grid-cols-2">
          {(["port", "data_dir"] as const).map((key) => (
            <Field key={key}>
              <FieldLabel htmlFor={`startup-${key}`}>{key === "port" ? "端口" : "数据目录"}</FieldLabel>
              {data.read_only[key] ? (
                <Input id={`startup-${key}`} readOnly value={String(data.effective[key])} aria-describedby={`${key}-reason`} />
              ) : (
                <Input
                  id={`startup-${key}`}
                  value={key === "port" ? current.port : current.data_dir}
                  onChange={(e) => set(key === "port" ? { port: e.target.value } : { data_dir: e.target.value })}
                />
              )}
              <FieldDescription>
                {data.read_only[key] ?? `生效中：${String(data.effective[key])}`}
              </FieldDescription>
            </Field>
          ))}

          <Field>
            <FieldLabel htmlFor="startup-backend">向量后端</FieldLabel>
            <Select value={current.vector_backend} onValueChange={(v) => set({ vector_backend: v })}>
              <SelectTrigger id="startup-backend" aria-label="向量后端">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BACKENDS.map((b) => (
                  <SelectItem key={b.value} value={b.value}>
                    {b.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription>生效中：{String(data.effective.vector_backend)}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="startup-debug">调试日志</FieldLabel>
            <div className="flex items-center gap-3">
              <Switch id="startup-debug" aria-label="调试日志" checked={current.debug} onCheckedChange={(checked) => set({ debug: checked })} />
              <span className="text-sm">{current.debug ? "开启" : "关闭"}</span>
            </div>
            <FieldDescription>生效中：{data.effective.debug ? "开启" : "关闭"}</FieldDescription>
          </Field>
        </div>

        <Separator className="bg-border/60" />

        <div className="flex flex-col gap-2">
          <span className="text-sm text-muted-foreground">
            向量模型 {String(data.effective.embedding_model)} · {String(data.effective.embedding_dim)} 维（只在配置文件里改：已存的向量是用它算出来的）
          </span>
          {Object.keys(data.draft).length ? (
            <span className="text-sm">
              待生效：
              <Badge variant="secondary" className="ml-1">
                {Object.entries(data.draft)
                  .map(([key, value]) => `${key} = ${String(value)}`)
                  .join("，")}
              </Badge>
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">没有待生效的改动。</span>
          )}
        </div>

        {problems ? (
          <Alert variant={problems.length ? "destructive" : "default"}>
            <AlertTitle>{problems.length ? "校验未通过" : "校验通过"}</AlertTitle>
            <AlertDescription>
              {problems.length ? (
                <ul className="list-inside list-disc">
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              ) : (
                "可以应用。"
              )}
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void saveDraft()} disabled={restarting || !Object.keys(changed).length}>
            保存为待生效
          </Button>
          <Button size="sm" variant="outline" onClick={() => void check()} disabled={restarting}>
            校验
          </Button>
          <Button size="sm" variant="outline" onClick={() => void apply()} disabled={restarting || !Object.keys(data.draft).length}>
            {restarting ? "重启中…" : "应用并重启"}
          </Button>
          {Object.keys(data.draft).length ? (
            <Button size="sm" variant="ghost" onClick={() => void discard()} disabled={restarting}>
              丢弃待生效
            </Button>
          ) : null}
        </div>

        <div className="text-sm text-muted-foreground">
          上次应用：
          {data.last_apply ? (
            <>
              <Badge variant={data.last_apply.status === "failed" ? "destructive" : "secondary"} className="mx-1">
                {APPLY_STATUS[data.last_apply.status] ?? data.last_apply.status}
              </Badge>
              {when(data.last_apply.finished_at ?? data.last_apply.at)}
              {data.last_apply.reason ? ` · ${data.last_apply.reason}` : ""}
            </>
          ) : (
            "还没有应用过"
          )}
        </div>
      </CardContent>
    </Card>
  );
}
