// Model providers (issue #12): add, edit, test, delete. Keys are write-only — the list shows the
// last four characters and an edit without a new key keeps the stored one. The provider from the
// configuration file is editable as an override and revertible, but not deletable.
import { useForm } from "@tanstack/react-form";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorState, Loading } from "@/components/page";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, enc, failed } from "@/lib/api";
import { keys, useProviders } from "@/lib/queries";
import { when } from "@/lib/terms";
import type { Provider, ProviderTest } from "@/lib/types";

const PROTOCOLS = [
  { value: "openai", label: "OpenAI 兼容" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Gemini" },
] as const;

const PLACEHOLDER: Record<Provider["protocol"], string> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
};

const PROTOCOL_LABEL = Object.fromEntries(PROTOCOLS.map((p) => [p.value, p.label])) as Record<Provider["protocol"], string>;

function LastCall({ p }: { p: Provider }) {
  if (p.last_call_at === null) return <span className="text-xs text-muted-foreground">从未调用</span>;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`flex items-center gap-1.5 text-[11px] ${p.last_call_ok ? "text-[var(--success)]" : "text-destructive"}`}>
          <span className={`size-1.5 rounded-full ${p.last_call_ok ? "bg-[var(--success)]" : "bg-destructive"}`} />
          {p.last_call_ok ? "成功" : "失败"}
        </span>
        <span className="text-[11px] text-muted-foreground tabular-nums">{when(p.last_call_at)}</span>
      </div>
      {p.last_call_ok === false && p.last_call_error ? (
        <span className="line-clamp-2 text-xs break-all text-destructive" title={p.last_call_error}>
          {p.last_call_error}
        </span>
      ) : null}
    </div>
  );
}

function Delete({ p }: { p: Provider }) {
  const queryClient = useQueryClient();
  const remove = async () => {
    try {
      await api(`/providers/${enc(p.id)}`, { method: "DELETE" });
      queryClient.setQueryData<Provider[]>(keys.providers, (old) => old?.filter((x) => x.id !== p.id));
      toast.success(`已删除「${p.name}」`);
    } catch (error) {
      failed(error);
    }
  };
  if (!p.deletable) return null;
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm">
          删除
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>删除「{p.name}」？</AlertDialogTitle>
          <AlertDialogDescription>删除后使用这个 Provider 的模型用途需要重新指定，已有的 API key 不能恢复。</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => void remove()}>
            删除
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function ProviderDialog({ provider, onClose }: { provider: Provider | "new"; onClose: () => void }) {
  const queryClient = useQueryClient();
  const editing = provider === "new" ? null : provider;
  const [error, setError] = useState("");
  const [test, setTest] = useState<ProviderTest | null>(null);

  const store = (next: Provider) =>
    queryClient.setQueryData<Provider[]>(keys.providers, (old) =>
      old ? (old.some((x) => x.id === next.id) ? old.map((x) => (x.id === next.id ? next : x)) : [...old, next]) : [next],
    );

  const form = useForm({
    defaultValues: {
      name: editing?.name ?? "",
      protocol: editing?.protocol ?? ("openai" as Provider["protocol"]),
      base_url: editing?.base_url ?? "",
      api_key: "",
    },
    onSubmit: async ({ value }) => {
      if (!value.name.trim() || !value.base_url.trim()) {
        setError("名称与地址不能为空");
        return;
      }
      setError("");
      try {
        if (!editing) {
          if (!value.api_key.trim()) {
            setError("请填写 API key");
            return;
          }
          const created = await api<Provider>("/providers", {
            method: "POST",
            body: { name: value.name, protocol: value.protocol, base_url: value.base_url, api_key: value.api_key },
          });
          store(created);
          toast.success(`已添加「${created.name}」`);
        } else {
          const body: Record<string, unknown> = {};
          if (value.name !== editing.name) body.name = value.name;
          if (editing.source !== "file" && value.protocol !== editing.protocol) body.protocol = value.protocol;
          if (value.base_url !== editing.base_url) body.base_url = value.base_url;
          if (value.api_key) body.api_key = value.api_key;
          if (Object.keys(body).length === 0) {
            onClose();
            return;
          }
          const next = await api<Provider>(`/providers/${enc(editing.id)}`, { method: "PUT", body });
          store(next);
          toast.success(`已保存「${next.name}」`);
        }
        onClose();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? `编辑「${editing.name}」` : "添加 Provider"}</DialogTitle>
          <DialogDescription>
            {editing?.source === "file"
              ? "这是配置文件里的 Provider。在这里修改会覆盖配置文件的值，可以随时恢复。"
              : "协议决定请求格式；地址要包含版本前缀，例如 https://api.openai.com/v1。"}
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void form.handleSubmit();
          }}
        >
          <form.Field name="name">
            {(f) => (
              <Field>
                <FieldLabel htmlFor="provider-name">名称</FieldLabel>
                <Input id="provider-name" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} />
              </Field>
            )}
          </form.Field>
          <form.Field name="protocol">
            {(f) => (
              <Field>
                <FieldLabel htmlFor="provider-protocol">协议</FieldLabel>
                <Select
                  value={f.state.value}
                  onValueChange={(v) => f.handleChange(v as Provider["protocol"])}
                  disabled={editing?.source === "file"}
                >
                  <SelectTrigger id="provider-protocol" aria-label="协议">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PROTOCOLS.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>
                  {editing?.source === "file" ? "配置文件里的 Provider 固定为 OpenAI 兼容，向量用途依赖它。" : "接口遵循哪一种协议。"}
                </FieldDescription>
              </Field>
            )}
          </form.Field>
          <form.Field name="base_url">
            {(f) => (
              <Field>
                <FieldLabel htmlFor="provider-url">地址</FieldLabel>
                <Input
                  id="provider-url"
                  className="font-mono text-xs"
                  placeholder={PLACEHOLDER[f.state.value as Provider["protocol"]]}
                  value={f.state.value}
                  onChange={(e) => f.handleChange(e.target.value)}
                />
                {editing?.source === "file" ? (
                  <FieldDescription>配置文件值：{editing.file_base_url}</FieldDescription>
                ) : null}
              </Field>
            )}
          </form.Field>
          <form.Field name="api_key">
            {(f) => (
              <Field>
                <FieldLabel htmlFor="provider-key">API key</FieldLabel>
                <Input
                  id="provider-key"
                  type="password"
                  autoComplete="off"
                  placeholder={editing?.has_key ? `已保存 ····${editing.api_key_last4}，留空则不修改` : "sk-..."}
                  value={f.state.value}
                  onChange={(e) => f.handleChange(e.target.value)}
                />
                <FieldDescription>只保存密文，之后只显示末四位。换 key 时直接填新的。</FieldDescription>
              </Field>
            )}
          </form.Field>
          {error ? <FieldError>{error}</FieldError> : null}
          {test ? (
            <p className={test.ok ? "text-sm" : "text-sm text-destructive"}>
              {test.ok
                ? `连接成功${test.checked ? `（用 ${test.checked} 试调用）` : ""}，可列出 ${test.models} 个模型：${test.sample.join("、")}`
                : test.error}
            </p>
          ) : null}
          <DialogFooter className="gap-2 sm:justify-between">
            <form.Subscribe selector={(s) => [s.values.protocol, s.values.base_url, s.values.api_key, s.isSubmitting] as const}>
              {([protocol, baseUrl, apiKey, busy]) => (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy || !baseUrl.trim()}
                  onClick={() =>
                    void api<ProviderTest>("/providers/test", {
                      method: "POST",
                      body: { id: editing?.id, protocol, base_url: baseUrl, api_key: apiKey || undefined },
                    })
                      .then(setTest)
                      .catch((e) =>
                        setTest({ ok: false, models: 0, sample: [], checked: null, reply: null, error: e instanceof Error ? e.message : String(e) }),
                      )
                  }
                >
                  测试连接
                </Button>
              )}
            </form.Subscribe>
            <form.Subscribe selector={(s) => s.isSubmitting}>
              {(busy) => (
                <Button type="submit" disabled={busy}>
                  {editing ? "保存" : "添加"}
                </Button>
              )}
            </form.Subscribe>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Revert one overridden field of the configuration-file provider to its file value. */
function Revert({ p, field }: { p: Provider; field: "base_url" | "api_key" }) {
  const queryClient = useQueryClient();
  const revert = async () => {
    try {
      const next = await api<Provider>(`/providers/${enc(p.id)}`, { method: "PUT", body: { [field]: null } });
      queryClient.setQueryData<Provider[]>(keys.providers, (old) => old?.map((x) => (x.id === next.id ? next : x)));
      toast.success(`${field === "base_url" ? "地址" : "API key"}已恢复为配置文件值`);
    } catch (error) {
      failed(error);
    }
  };
  if (!p.overridden[field]) return null;
  return (
    <Button variant="ghost" size="sm" onClick={() => void revert()}>
      恢复{field === "base_url" ? "地址" : "key"}
    </Button>
  );
}

export function ProvidersSection() {
  const providers = useProviders();
  const [editing, setEditing] = useState<Provider | "new" | null>(null);
  return (
    <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/70 px-5 py-4">
        <CardTitle className="text-[13px] font-medium">Provider</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-5 py-4">
        <div>
          <Button size="sm" onClick={() => setEditing("new")}>添加 Provider</Button>
        </div>
        {providers.error && <ErrorState error={providers.error} onRetry={() => void providers.refetch()} />}
        {providers.isPending && <Loading rows={2} />}
        {providers.data && (
          <Table>
            <TableHeader>
              <TableRow className="border-border/70 hover:bg-transparent">
                <TableHead className="h-9 px-3 text-[11px] font-medium text-muted-foreground">名称</TableHead>
                <TableHead className="hidden h-9 px-3 text-[11px] font-medium text-muted-foreground md:table-cell">地址</TableHead>
                <TableHead className="hidden h-9 px-3 text-[11px] font-medium text-muted-foreground lg:table-cell">API key</TableHead>
                <TableHead className="h-9 px-3 text-[11px] font-medium text-muted-foreground">最近调用</TableHead>
                <TableHead className="h-9 px-3">
                  <span className="sr-only">操作</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {providers.data.map((p) => (
                <TableRow key={p.id} className="border-border/60">
                  <TableCell className="px-3 py-3 whitespace-normal">
                    <div className="text-[13px] font-medium break-all">{p.name}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <Badge variant={p.source === "console" ? "default" : "secondary"}>
                        {p.source === "console" ? "面板" : "配置文件"}
                      </Badge>
                      <Badge variant="outline">{PROTOCOL_LABEL[p.protocol]}</Badge>
                    </div>
                  </TableCell>
                  <TableCell className="hidden max-w-[16rem] truncate px-3 py-3 font-mono text-[11px] text-muted-foreground md:table-cell">
                    {p.base_url}
                  </TableCell>
                  <TableCell className="hidden px-3 py-3 font-mono text-[11px] text-muted-foreground lg:table-cell">
                    {p.has_key ? `····${p.api_key_last4}` : "未设置"}
                  </TableCell>
                  <TableCell className="px-3 py-3">
                    <LastCall p={p} />
                  </TableCell>
                  <TableCell className="px-3 py-3 text-right whitespace-nowrap">
                    <Button variant="ghost" size="sm" onClick={() => setEditing(p)}>
                      编辑
                    </Button>
                    <Revert p={p} field="base_url" />
                    <Revert p={p} field="api_key" />
                    <Delete p={p} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {editing !== null && (
          <ProviderDialog
            key={editing === "new" ? "new" : editing.id}
            provider={editing}
            onClose={() => setEditing(null)}
          />
        )}
      </CardContent>
    </Card>
  );
}
