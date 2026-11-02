// Model roles (issue #13): the write and maintenance roles each choose a provider, model and
// timeout; the embedding role is read-only because stored vectors depend on it.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorState, Loading } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, enc, failed } from "@/lib/api";
import { keys, useModelRoles, useModels, useProviders } from "@/lib/queries";
import type { ModelRole, Provider, RoleTest } from "@/lib/types";

const DESCRIPTION: Record<string, string> = {
  write: "remember 时的 key 分配、合并与冲突判定。写入要快，模型只需稳定地输出结构化结果。",
  maintenance: "后台检查的判定：内部矛盾、跨 key 重复。可以用更强的模型，不影响写入速度。",
};

function RoleRow({ role, providers }: { role: ModelRole; providers: Provider[] }) {
  const queryClient = useQueryClient();
  const [providerId, setProviderId] = useState(role.provider_id);
  const [model, setModel] = useState(role.model);
  const [timeout, setTimeout] = useState(String(role.timeout));
  const [test, setTest] = useState<RoleTest | null>(null);
  const [error, setError] = useState("");
  const models = useModels(providerId);
  const dirty = providerId !== role.provider_id || model !== role.model || Number(timeout) !== role.timeout;

  const store = (next: ModelRole) =>
    queryClient.setQueryData<ModelRole[]>(keys.roles, (old) => old?.map((x) => (x.role === next.role ? next : x)));

  const save = async () => {
    setError("");
    try {
      const next = await api<ModelRole>(`/model-roles/${enc(role.role)}`, {
        method: "PUT",
        body: { provider_id: providerId, model, timeout: Number(timeout) },
      });
      store(next);
      toast.success(`${role.label}用途已保存`);
    } catch (e) {
      failed(e);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const clear = async () => {
    try {
      const next = await api<ModelRole>(`/model-roles/${enc(role.role)}`, { method: "DELETE" });
      store(next);
      setProviderId(next.provider_id);
      setModel(next.model);
      setTimeout(String(next.timeout));
      toast.success(`${role.label}用途已恢复默认`);
    } catch (e) {
      failed(e);
    }
  };

  const runTest = async () => {
    setTest(null);
    try {
      setTest(await api<RoleTest>(`/model-roles/${enc(role.role)}/test`, { method: "POST" }));
    } catch (e) {
      setTest({ ok: false, reply: null, error: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <div className="flex flex-col gap-4 py-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">{role.label}</h3>
        <Badge variant={role.custom ? "default" : "secondary"}>{role.custom ? "自定义" : "默认"}</Badge>
        {role.defaults ? (
          <span className="text-xs text-muted-foreground">
            默认：{role.defaults.provider_name} · {role.defaults.model} · {role.defaults.timeout} 秒
          </span>
        ) : null}
      </div>
      <p className="text-sm text-muted-foreground">{DESCRIPTION[role.role]}</p>
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_8rem]">
        <Field>
          <FieldLabel htmlFor={`${role.role}-provider`}>Provider</FieldLabel>
          <Select value={providerId} onValueChange={setProviderId}>
            <SelectTrigger id={`${role.role}-provider`} aria-label={`${role.label}用途的 Provider`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor={`${role.role}-model`}>模型</FieldLabel>
          <Input
            id={`${role.role}-model`}
            className="font-mono text-xs"
            list={`${role.role}-models`}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <datalist id={`${role.role}-models`}>
            {(models.data ?? []).map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <FieldDescription>
            {models.error ? "取不到模型列表，可以直接填写模型 id。" : "从该 Provider 的模型列表里选，或直接填写 id。"}
          </FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor={`${role.role}-timeout`}>超时（秒）</FieldLabel>
          <Input
            id={`${role.role}-timeout`}
            inputMode="decimal"
            className="tabular-nums"
            value={timeout}
            onChange={(e) => setTimeout(e.target.value)}
          />
        </Field>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {test ? (
        <p className={test.ok ? "text-sm" : "text-sm text-destructive"}>
          {test.ok ? `调用成功：${test.reply}` : test.error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => void save()} disabled={!model.trim() || !timeout.trim()}>
          保存
        </Button>
        <Button size="sm" variant="outline" onClick={() => void runTest()}>
          测试调用
        </Button>
        {role.custom ? (
          <Button size="sm" variant="outline" onClick={() => void clear()}>
            恢复默认
          </Button>
        ) : null}
        {dirty ? <span className="self-center text-xs text-muted-foreground">有未保存的修改</span> : null}
      </div>
    </div>
  );
}

export function RolesSection() {
  const roles = useModelRoles();
  const providers = useProviders();
  const embedding = roles.data?.find((r) => r.read_only);
  return (
    <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/70 px-5 py-4">
        <CardTitle className="text-[13px] font-medium">模型用途</CardTitle>
        <CardDescription className="text-xs">
          每一类模型调用用哪个 Provider、模型与超时。保存后下一次调用即生效，无需重启。
        </CardDescription>
      </CardHeader>
      <CardContent className="px-5">
        {roles.error && <ErrorState error={roles.error} onRetry={() => void roles.refetch()} />}
        {roles.isPending && <Loading rows={2} />}
        {roles.data && providers.data ? (
          <>
            {roles.data
              .filter((r) => !r.read_only)
              .map((role, i) => (
                <div key={role.role}>
                  {i > 0 && <Separator className="bg-border/60" />}
                  <RoleRow role={role} providers={providers.data} />
                </div>
              ))}
            {embedding ? <Separator className="bg-border/60" /> : null}
            {embedding ? (
              <div className="flex flex-col gap-2 py-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-medium">{embedding.label}</h3>
                  <Badge variant="secondary">只读</Badge>
                </div>
                <p className="text-sm text-muted-foreground">
                  {embedding.provider_name} · {embedding.model} · {embedding.dimension} 维。已存的向量是用它算出来的，改了这个模型就无法与存量比较，所以只能在配置文件里改，并且要重建全部向量。
                </p>
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
