// Settings: behaviour and tuning parameters from the settings registry (issue #9). Each setting shows
// its value, where the value comes from, and can revert to the configuration file value.
import { useForm } from "@tanstack/react-form";
import { useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useId } from "react";
import { toast } from "sonner";

import { ErrorState, Loading, PageBody, PageHeader } from "@/components/page";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldContent, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useIsMobile } from "@/hooks/use-mobile";
import { api, enc, failed } from "@/lib/api";
import { keys, useSettings } from "@/lib/queries";
import { invalidReason } from "@/lib/settings";
import { SOURCE } from "@/lib/terms";
import { ProvidersSection } from "@/pages/providers";
import { RolesSection } from "@/pages/roles";
import { SecuritySection } from "@/pages/security";
import { StartupSection } from "@/pages/startup";
import { TokensSection } from "@/pages/tokens";
import type { Setting } from "@/lib/types";
import { cn } from "@/lib/utils";

const TABS = [
  { value: "parameters", label: "参数" },
  { value: "providers", label: "Provider" },
  { value: "roles", label: "模型用途" },
  { value: "tokens", label: "访问令牌" },
  { value: "startup", label: "启动设置" },
  { value: "security", label: "安全" },
];

function SettingRow({ s }: { s: Setting }) {
  const queryClient = useQueryClient();
  const id = useId();
  const differs = s.recommended !== null && s.value !== s.recommended;

  const save = async (value: number | boolean | null) => {
    try {
      const next = await api<Setting>(`/settings/${enc(s.key)}`, value === null ? { method: "DELETE" } : { method: "PUT", body: { value } });
      queryClient.setQueryData<Setting[]>(keys.settings, (old) => old?.map((x) => (x.key === s.key ? next : x)));
      toast.success(value === null ? `${s.label}已恢复为${SOURCE[next.source]}` : `${s.label}已保存`);
      return next;
    } catch (error) {
      failed(error);
      return null;
    }
  };

  const form = useForm({
    defaultValues: { value: String(s.value) },
    onSubmit: async ({ value, formApi }) => {
      const next = await save(Number(value.value));
      if (next) formApi.reset({ value: String(next.value) });
    },
  });

  return (
    <div className="grid gap-4 py-5 md:grid-cols-[minmax(0,1fr)_18rem]">
      <FieldContent>
        <div className="flex flex-wrap items-center gap-2">
          <FieldLabel htmlFor={id}>{s.label}</FieldLabel>
          <Badge variant={s.source === "console" ? "default" : "secondary"} className="h-4 text-[10px]">
            来源：{SOURCE[s.source]}
          </Badge>
        </div>
        <code className="mt-0.5 block font-mono text-[10px] break-all text-muted-foreground/80">{s.key}</code>
        <FieldDescription>{s.description}</FieldDescription>
        {s.recommended !== null && (
          <FieldDescription>
            推荐值 <span className="font-medium text-foreground tabular-nums">{s.recommended}</span>。{s.note}
          </FieldDescription>
        )}
        {s.source === "console" && (
          <FieldDescription>
            {s.file_value !== null ? "配置文件为" : "默认值为"}{" "}
            <span className="tabular-nums">
              {typeof (s.file_value ?? s.default) === "boolean"
                ? (s.file_value ?? s.default)
                  ? "开启"
                  : "关闭"
                : (s.file_value ?? s.default)}
            </span>
          </FieldDescription>
        )}
      </FieldContent>
      {s.type === "bool" ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <Switch id={id} aria-label={s.label} checked={Boolean(s.value)} onCheckedChange={(checked) => void save(checked)} />
            <span className="text-sm">{s.value ? "开启" : "关闭"}</span>
          </div>
          {s.source === "console" && (
            <Button type="button" variant="outline" size="sm" onClick={() => void save(null)}>
              恢复为{s.file_value !== null ? "配置文件值" : "默认值"}
            </Button>
          )}
        </div>
      ) : (
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void form.handleSubmit();
        }}
      >
        <form.Field name="value" validators={{ onChange: ({ value }) => invalidReason(s, value) || undefined }}>
          {(field) => {
            const error = field.state.meta.errors[0];
            return (
              <Field data-invalid={!!error || undefined}>
                <div className="flex gap-2">
                  <Input
                    id={id}
                    inputMode="decimal"
                    className="h-9 bg-card tabular-nums"
                    aria-invalid={!!error}
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                  />
                  <form.Subscribe selector={(st) => [st.isDirty, st.canSubmit, st.isSubmitting] as const}>
                    {([dirty, can, busy]) => (
                      <Button type="submit" variant={dirty ? "default" : "outline"} disabled={!dirty || !can || busy}>
                        保存
                      </Button>
                    )}
                  </form.Subscribe>
                </div>
                {error ? <FieldError>{String(error)}</FieldError> : <FieldDescription>范围 {s.min} – {s.max}</FieldDescription>}
              </Field>
            );
          }}
        </form.Field>
        {differs && (
          <Alert className="border-[var(--warning)]/25 bg-[var(--warning)]/5">
            <TriangleAlert className="text-[var(--warning)]" />
            <AlertDescription>与推荐值不同，检索或维护效果可能下降。</AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap gap-2">
          {differs && (
            <Button type="button" variant="outline" size="sm" onClick={() => void save(s.recommended)}>
              恢复推荐值
            </Button>
          )}
          {s.source === "console" && (
            <Button type="button" variant="outline" size="sm" onClick={() => void save(null)}>
              恢复为{s.file_value !== null ? "配置文件值" : "默认值"}
            </Button>
          )}
        </div>
      </form>
      )}
    </div>
  );
}

function Section({ title, description, items }: { title: string; description: string; items: Setting[] }) {
  return (
    <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/70 px-5 py-4">
        <CardTitle className="text-[13px] font-medium">{title}</CardTitle>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent className="px-5">
        {items.map((s, i) => (
          <div key={`${s.key}:${s.source}:${s.value}`} className={cn(i > 0 && "border-t border-border/60")}>
            <SettingRow s={s} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function SettingsPage() {
  const settings = useSettings();
  const isMobile = useIsMobile();

  return (
    <>
      <PageHeader title="设置" description="参数、模型、令牌与启动选项。" />
      <PageBody>
        <Tabs
          defaultValue="parameters"
          orientation={isMobile ? "horizontal" : "vertical"}
          className="flex flex-col gap-6 md:flex-row md:items-start"
        >
          <TabsList
            variant="line"
            className={cn(
              "h-auto! w-full justify-start gap-1 rounded-none border-b border-border/70 p-0 pb-2 flex-wrap md:sticky md:top-0 md:w-48 md:flex-col md:items-stretch md:border-b-0 md:pb-0",
            )}
          >
            {TABS.map((t, i) => (
              <TabsTrigger
                key={t.value}
                value={t.value}
                className="h-9 flex-none justify-start rounded-lg px-2.5 text-[13px] text-muted-foreground after:hidden data-active:bg-card data-active:text-foreground data-active:shadow-[0_1px_2px_rgba(23,24,26,0.06)]"
              >
                <span aria-hidden="true" className="mr-2 font-mono text-[10px] text-muted-foreground/60">{String(i + 1).padStart(2, "0")}</span>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <div className="min-w-0 flex-1">
            <TabsContent value="parameters" className="mt-0 flex flex-col gap-4">
              <p className="max-w-[70ch] text-xs leading-6 text-muted-foreground">
                这里保存的值优先于配置文件，保存后下一次调用即生效，无需重启。恢复后改用配置文件里的值；配置文件没有设置时用默认值。
              </p>
              {settings.error && <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />}
              {settings.isPending && <Loading />}
              {settings.data && (
                <>
                  <Section title="行为参数" description="写入合并与后台维护的行为。" items={settings.data.filter((s) => s.group === "behaviour")} />
                  <Section
                    title="高级参数"
                    description="混合检索与维护检查里经线上评估定下的数值。偏离推荐值前先确认评估依据。"
                    items={settings.data.filter((s) => s.group === "advanced")}
                  />
                </>
              )}
            </TabsContent>
            <TabsContent value="providers" className="mt-0 flex flex-col gap-4">
              <ProvidersSection />
            </TabsContent>
            <TabsContent value="roles" className="mt-0 flex flex-col gap-4">
              <RolesSection />
            </TabsContent>
            <TabsContent value="tokens" className="mt-0 flex flex-col gap-4">
              <TokensSection />
            </TabsContent>
            <TabsContent value="startup" className="mt-0 flex flex-col gap-4">
              <StartupSection />
            </TabsContent>
            <TabsContent value="security" className="mt-0 flex flex-col gap-4">
              <SecuritySection />
            </TabsContent>
          </div>
        </Tabs>
      </PageBody>
    </>
  );
}
