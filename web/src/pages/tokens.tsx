// Access tokens (issue #11): list, create (value shown once), revoke. The initial token from the
// configuration file is an ordinary token; only its source differs.
import { useForm } from "@tanstack/react-form";
import { useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, AuthError, enc, failed } from "@/lib/api";
import { keys, useTokens } from "@/lib/queries";
import { when } from "@/lib/terms";
import type { AccessToken } from "@/lib/types";

function State({ t }: { t: AccessToken }) {
  return t.revoked_at === null ? <Badge variant="secondary">启用中</Badge> : <Badge variant="outline">已吊销</Badge>;
}

function Revoke({ t }: { t: AccessToken }) {
  const queryClient = useQueryClient();
  const revoke = async () => {
    try {
      const next = await api<AccessToken>(`/tokens/${enc(t.id)}`, { method: "DELETE" });
      queryClient.setQueryData<AccessToken[]>(keys.tokens, (old) => old?.map((x) => (x.id === next.id ? next : x)));
      toast.success(`已吊销「${t.name}」`);
    } catch (error) {
      failed(error);
    }
  };
  if (t.revoked_at !== null) return null;
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="sm">
          吊销
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>吊销「{t.name}」？</AlertDialogTitle>
          <AlertDialogDescription>
            {t.source === "file"
              ? "吊销后，仍在使用配置文件里那个令牌的客户端（包括宿主机上的维护定时任务）会被拒绝，面板不能恢复。只有在部署主机上执行口令重置命令时，它才会按配置文件里的值重新生效。"
              : "吊销后使用这个令牌的客户端会被拒绝，不能恢复。名称会保留，不能再用于新令牌。"}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => void revoke()}>
            吊销
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function CreatedDialog({ created, onClose }: { created: { name: string; value: string } | null; onClose: () => void }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(created!.value);
      toast.success("已复制");
    } catch {
      toast.error("复制失败，请手动选中复制");
    }
  };
  return (
    <Dialog open={created !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>已创建「{created?.name}」</DialogTitle>
          <DialogDescription>令牌只显示这一次。关闭后无法再查看，丢失时吊销并新建一个。</DialogDescription>
        </DialogHeader>
        <InputGroup>
          <InputGroupInput readOnly aria-label="令牌" className="font-mono text-xs" value={created?.value ?? ""} onFocus={(e) => e.target.select()} />
          <InputGroupAddon align="inline-end">
            <InputGroupButton aria-label="复制" onClick={() => void copy()}>
              <Copy />
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
        <DialogFooter>
          <Button onClick={onClose}>我已保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CreateToken() {
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [created, setCreated] = useState<{ name: string; value: string } | null>(null);
  const form = useForm({
    defaultValues: { name: "" },
    onSubmit: async ({ value, formApi }) => {
      if (!value.name.trim()) {
        setError("名称不能为空");
        return;
      }
      setError("");
      try {
        const { value: secret, ...token } = await api<AccessToken & { value: string }>("/tokens", { method: "POST", body: { name: value.name } });
        queryClient.setQueryData<AccessToken[]>(keys.tokens, (old) => [...(old ?? []), token]);
        setCreated({ name: token.name, value: secret });
        formApi.reset();
      } catch (e) {
        // A lost session already returned to sign-in; anything else is shown under the field.
        if (!(e instanceof AuthError)) setError(e instanceof Error ? e.message : String(e));
      }
    },
  });
  return (
    <>
      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-start"
        onSubmit={(e) => {
          e.preventDefault();
          void form.handleSubmit();
        }}
      >
        <form.Field name="name">
          {(f) => (
            <Field data-invalid={!!error || undefined} className="sm:max-w-xs">
              <FieldLabel htmlFor="token-name" className="sr-only">
                名称
              </FieldLabel>
              <Input
                id="token-name"
                placeholder="名称，如主机名或 cli"
                aria-invalid={!!error}
                value={f.state.value}
                onChange={(e) => f.handleChange(e.target.value)}
              />
              {error ? <FieldError>{error}</FieldError> : null}
            </Field>
          )}
        </form.Field>
        <form.Subscribe selector={(s) => s.isSubmitting}>
          {(busy) => (
            <Button type="submit" disabled={busy}>
              创建令牌
            </Button>
          )}
        </form.Subscribe>
      </form>
      <CreatedDialog created={created} onClose={() => setCreated(null)} />
    </>
  );
}

export function TokensSection() {
  const tokens = useTokens();
  return (
    <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/70 px-5 py-4">
        <CardTitle className="text-[13px] font-medium">访问令牌</CardTitle>
        <CardDescription className="text-xs">
          agent、CLI 与维护定时任务调用 MCP 和 REST 时使用。令牌只能读写记忆与发现，不能修改设置。写入的记忆会记下令牌名称。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-5 py-4">
        <CreateToken />
        {tokens.error && <ErrorState error={tokens.error} onRetry={() => void tokens.refetch()} />}
        {tokens.isPending && <Loading rows={2} />}
        {tokens.data && (
          <Table>
            <TableHeader>
              <TableRow className="border-border/70 hover:bg-transparent">
                <TableHead className="h-9 px-3 text-[11px] font-medium text-muted-foreground">名称</TableHead>
                <TableHead className="hidden h-9 px-3 text-[11px] font-medium text-muted-foreground md:table-cell">来源</TableHead>
                <TableHead className="hidden h-9 px-3 text-[11px] font-medium text-muted-foreground md:table-cell">创建</TableHead>
                <TableHead className="h-9 px-3 text-[11px] font-medium text-muted-foreground">最近使用</TableHead>
                <TableHead className="h-9 px-3">
                  <span className="sr-only">操作</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tokens.data.map((t) => (
                <TableRow key={t.id} className="border-border/60">
                  <TableCell className="px-3 py-3 whitespace-normal break-all">
                    <div className="text-[13px] font-medium">{t.name}</div>
                    <div className="mt-1">
                      <State t={t} />
                    </div>
                  </TableCell>
                  <TableCell className="hidden px-3 py-3 text-[11px] text-muted-foreground md:table-cell">{t.source === "file" ? "配置文件" : "面板"}</TableCell>
                  <TableCell className="hidden px-3 py-3 text-[11px] text-muted-foreground tabular-nums md:table-cell">{when(t.created_at)}</TableCell>
                  <TableCell className="px-3 py-3 text-[11px] text-muted-foreground tabular-nums">{t.last_used_at ? when(t.last_used_at) : "从未使用"}</TableCell>
                  <TableCell className="px-3 py-3 text-right">
                    <Revoke t={t} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
