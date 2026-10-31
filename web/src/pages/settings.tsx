// Settings: behaviour and tuning parameters from the settings registry (issue #9). Each setting shows
// its value, where the value comes from, and can revert to the configuration file value.
import { useForm } from "@tanstack/react-form";
import { useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useId } from "react";
import { toast } from "sonner";

import { ErrorState, Loading, PageHeader } from "@/components/page";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldContent, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { api, enc, failed } from "@/lib/api";
import { keys, useSettings } from "@/lib/queries";
import { invalidReason } from "@/lib/settings";
import { SOURCE } from "@/lib/terms";
import type { Setting } from "@/lib/types";

function SettingRow({ s }: { s: Setting }) {
  const queryClient = useQueryClient();
  const id = useId();
  const differs = s.recommended !== null && s.value !== s.recommended;

  const save = async (value: number | null) => {
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
    <div className="grid gap-4 py-5 md:grid-cols-[minmax(0,1fr)_20rem]">
      <FieldContent>
        <div className="flex flex-wrap items-center gap-2">
          <FieldLabel htmlFor={id}>{s.label}</FieldLabel>
          <code className="text-xs text-muted-foreground">{s.key}</code>
          <Badge variant={s.source === "console" ? "default" : "secondary"}>来源：{SOURCE[s.source]}</Badge>
        </div>
        <FieldDescription>{s.description}</FieldDescription>
        {s.recommended !== null && (
          <FieldDescription>
            推荐值 <span className="font-medium text-foreground tabular-nums">{s.recommended}</span>。{s.note}
          </FieldDescription>
        )}
        {s.source === "console" && (
          <FieldDescription>
            {s.file_value !== null ? "配置文件为" : "默认值为"} <span className="tabular-nums">{s.file_value ?? s.default}</span>
          </FieldDescription>
        )}
      </FieldContent>
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
                    className="tabular-nums"
                    aria-invalid={!!error}
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                  />
                  <form.Subscribe selector={(st) => [st.isDirty, st.canSubmit, st.isSubmitting] as const}>
                    {([dirty, can, busy]) => (
                      <Button type="submit" disabled={!dirty || !can || busy}>
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
          <Alert>
            <TriangleAlert />
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
    </div>
  );
}

function Section({ title, description, items }: { title: string; description: string; items: Setting[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {items.map((s, i) => (
          <div key={`${s.key}:${s.source}:${s.value}`}>
            {i > 0 && <Separator />}
            <SettingRow s={s} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function SettingsPage() {
  const settings = useSettings();
  return (
    <>
      <PageHeader title="设置" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4 md:p-6">
          <p className="text-sm text-muted-foreground">
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
        </div>
      </div>
    </>
  );
}
