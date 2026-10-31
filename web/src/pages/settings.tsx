// Settings: behaviour and tuning parameters from the settings registry (issue #9). Each setting shows
// its value, where the value comes from, and can revert to the configuration file value.
import { useForm } from "@tanstack/react-form";
import { useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useId } from "react";
import { toast } from "sonner";

import { ErrorNote, Skeleton, Stamp } from "@/components/registry";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, enc, failed } from "@/lib/api";
import { keys, useSettings } from "@/lib/queries";
import { SOURCE } from "@/lib/terms";
import { invalidReason } from "@/lib/settings";
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

  const resetTo = async (value: number | null) => {
    const next = await save(value);
    if (next) form.reset({ value: String(next.value) });
  };

  return (
    <li className="grid gap-x-8 gap-y-3 border-b border-rule py-5 md:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={id} className="font-semibold text-ink">
            {s.label}
          </label>
          <span className="font-mono text-xs text-ink-3">{s.key}</span>
        </div>
        <p className="mt-1 mb-0 max-w-[72ch] text-sm text-ink-2">{s.description}</p>
        {s.recommended !== null && (
          <p className="mt-2 mb-0 max-w-[72ch] text-[0.8125rem] text-ink-3">
            推荐值 <span className="font-mono tabular-nums text-ink-2">{s.recommended}</span>。{s.note}
          </p>
        )}
      </div>
      <form
        className="grid content-start gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void form.handleSubmit();
        }}
      >
        <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-ink-3">
          <span>来源</span>
          <Stamp tone={s.source === "console" ? "correction" : "plain"}>{SOURCE[s.source]}</Stamp>
          {s.source === "console" && (
            <span>
              {s.file_value !== null ? "配置文件为" : "默认值为"}{" "}
              <span className="font-mono tabular-nums">{s.file_value ?? s.default}</span>
            </span>
          )}
        </div>
        <form.Field name="value" validators={{ onChange: ({ value }) => invalidReason(s, value) || undefined }}>
          {(field) => {
            const error = field.state.meta.errors[0];
            return (
              <>
                <div className="flex gap-2">
                  <Input
                    id={id}
                    inputMode="decimal"
                    className="font-mono tabular-nums"
                    aria-invalid={!!error}
                    aria-describedby={`${id}-range`}
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                  />
                  <form.Subscribe selector={(st) => [st.isDirty, st.canSubmit, st.isSubmitting] as const}>
                    {([dirty, can, busy]) => (
                      <Button type="submit" variant="primary" disabled={!dirty || !can || busy}>
                        保存
                      </Button>
                    )}
                  </form.Subscribe>
                </div>
                <p id={`${id}-range`} role={error ? "alert" : undefined} className={`m-0 text-[0.8125rem] ${error ? "text-danger" : "text-ink-3"}`}>
                  {error ? String(error) : `范围 ${s.min} – ${s.max}`}
                </p>
              </>
            );
          }}
        </form.Field>
        {differs && (
          <p className="m-0 flex items-start gap-1.5 text-[0.8125rem] text-warn">
            <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
            与推荐值不同，检索或维护效果可能下降。
          </p>
        )}
        <div className="flex flex-wrap gap-1">
          {differs && (
            <Button variant="quiet" size="sm" className="-ml-2.5" onClick={() => void resetTo(s.recommended)}>
              恢复推荐值
            </Button>
          )}
          {s.source === "console" && (
            <Button variant="quiet" size="sm" className={differs ? "" : "-ml-2.5"} onClick={() => void resetTo(null)}>
              恢复为{s.file_value !== null ? "配置文件值" : "默认值"}
            </Button>
          )}
        </div>
      </form>
    </li>
  );
}

function Section({ title, intro, items }: { title: string; intro: string; items: Setting[] }) {
  return (
    <section className="mb-10" aria-labelledby={`section-${title}`}>
      <h2 id={`section-${title}`} className="m-0 text-lg font-[650]">
        {title}
      </h2>
      <p className="mt-1 mb-2 max-w-[72ch] text-sm text-ink-2">{intro}</p>
      <ul className="m-0 list-none border-t border-rule-strong p-0">
        {items.map((s) => (
          <SettingRow key={`${s.key}:${s.source}:${s.value}`} s={s} />
        ))}
      </ul>
    </section>
  );
}

export function SettingsPage() {
  const settings = useSettings();
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 pt-6 pb-16 md:px-8">
        <h1 className="m-0 mb-1 text-xl font-bold">设置</h1>
        <p className="mt-0 mb-8 max-w-[72ch] text-sm text-ink-2">
          这里保存的值优先于配置文件，保存后下一次调用即生效，无需重启。恢复后改用配置文件里的值；配置文件没有设置时用默认值。
        </p>
        {settings.error && <ErrorNote error={settings.error} onRetry={() => void settings.refetch()} />}
        {settings.isPending && (
          <>
            <Skeleton />
            <Skeleton className="w-[70%]" />
            <Skeleton className="w-[40%]" />
          </>
        )}
        {settings.data && (
          <>
            <Section
              title="行为参数"
              intro="写入合并与后台维护的行为。"
              items={settings.data.filter((s) => s.group === "behaviour")}
            />
            <Section
              title="高级参数"
              intro="混合检索与维护检查里经线上评估定下的数值。偏离推荐值前先确认评估依据。"
              items={settings.data.filter((s) => s.group === "advanced")}
            />
          </>
        )}
      </div>
    </div>
  );
}
