// Signed-out views: sign in with the admin password; on a fresh deployment, sign in once with the
// configuration-file access token, then set the admin password (docs/adr/0001).
import { useForm } from "@tanstack/react-form";
import { Eye, EyeOff } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { BrandMark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSession } from "@/lib/session";

function Frame({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <main className="grid min-h-svh bg-background lg:grid-cols-[1.08fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-[#141917] p-12 text-[#f2f0e9] lg:flex">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-[10px] bg-[#f2f0e9] text-[14px] font-semibold text-[#141917]">
            记
          </span>
          <span className="grid leading-tight">
            <span className="text-sm font-semibold">记忆登记簿</span>
            <span className="text-[9px] tracking-[0.16em] text-[#f2f0e9]/40">MEMORY REGISTRY</span>
          </span>
        </div>
        <div className="max-w-[26rem]">
          <p className="text-[10px] font-medium tracking-[0.16em] text-[#f2f0e9]/40">LONG-TERM MEMORY</p>
          <h2 className="mt-5 text-[40px] leading-[1.12] font-semibold tracking-[-0.035em]">
            把每一次判断，
            <br />
            留在版本里。
          </h2>
          <p className="mt-6 text-sm leading-6 text-[#f2f0e9]/55">
            机器找出问题，人只负责判断。
          </p>
        </div>
        <div className="grid grid-cols-3 gap-6 border-t border-[#f2f0e9]/10 pt-6">
          {[
            ["检查", "重复 · 矛盾 · 多版本"],
            ["检索", "向量 · 全文 · 图谱"],
            ["版本", "改正随时可追溯"],
          ].map(([label, note]) => (
            <div key={label}>
              <p className="text-xs font-medium text-[#f2f0e9]/80">{label}</p>
              <p className="mt-1 text-[11px] leading-4 text-[#f2f0e9]/40">{note}</p>
            </div>
          ))}
        </div>
        <span
          aria-hidden
          className="pointer-events-none absolute -right-24 -bottom-24 size-[28rem] rounded-full border border-[#f2f0e9]/[0.06]"
        />
        <span
          aria-hidden
          className="pointer-events-none absolute -right-6 -bottom-6 size-[16rem] rounded-full border border-[#f2f0e9]/[0.06]"
        />
      </section>

      <section className="flex items-center justify-center px-6 py-10 md:px-10">
        <div className="w-full max-w-[340px]">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <BrandMark />
            <span className="grid leading-tight">
              <span className="text-sm font-semibold">记忆登记簿</span>
              <span className="text-[9px] tracking-[0.14em] text-muted-foreground">MEMORY REGISTRY</span>
            </span>
          </div>
          <p className="eyebrow">CONSOLE</p>
          <h1 className="mt-2 text-[28px] leading-tight font-semibold tracking-[-0.025em]">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
          <div className="mt-8">{children}</div>
        </div>
      </section>
    </main>
  );
}

// Each view keys its form, so a value typed in one (the access token) never carries into the next.
function SecretForm({ id, label, hint, submit, autoComplete, onSubmit, confirm }: {
  id: string;
  label: string;
  hint: string;
  submit: string;
  autoComplete: string;
  onSubmit: (value: string) => Promise<void>;
  confirm?: boolean;
}) {
  const [error, setError] = useState("");
  const [show, setShow] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const secret = autoComplete === "off" ? "内容" : "口令";
  useEffect(() => input.current?.focus(), []);
  const form = useForm({
    defaultValues: { value: "", again: "" },
    onSubmit: async ({ value, formApi }) => {
      if (!value.value) return;
      if (confirm && value.value !== value.again) {
        setError("两次输入的口令不一致");
        return;
      }
      setError("");
      try {
        await onSubmit(value.value);
      } catch (e) {
        formApi.reset();
        setError(e instanceof Error ? e.message : String(e));
        input.current?.focus();
      }
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void form.handleSubmit();
      }}
    >
      <FieldGroup>
        <form.Field name="value">
          {(field) => (
            <Field data-invalid={!!error || undefined}>
              <FieldLabel htmlFor={id}>{label}</FieldLabel>
              <div className="relative">
                <Input
                  ref={input}
                  id={id}
                  type={show ? "text" : "password"}
                  autoComplete={autoComplete}
                  spellCheck={false}
                  required
                  aria-invalid={!!error}
                  className="h-10 pr-11"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="absolute top-1/2 right-1 -translate-y-1/2 text-muted-foreground"
                  aria-label={`${show ? "隐藏" : "显示"}${secret}`}
                  aria-pressed={show}
                  onClick={() => setShow((value) => !value)}
                >
                  {show ? <EyeOff /> : <Eye />}
                </Button>
              </div>
              {!confirm && (error ? <FieldError>{error}</FieldError> : <FieldDescription>{hint}</FieldDescription>)}
            </Field>
          )}
        </form.Field>
        {confirm && (
          <form.Field name="again">
            {(field) => (
              <Field data-invalid={!!error || undefined}>
                <FieldLabel htmlFor={`${id}-again`}>再输入一次</FieldLabel>
                <Input
                  id={`${id}-again`}
                  type="password"
                  autoComplete={autoComplete}
                  required
                  className="h-10"
                  value={field.state.value}
                  onChange={(e) => field.handleChange(e.target.value)}
                />
                {error ? <FieldError>{error}</FieldError> : <FieldDescription>{hint}</FieldDescription>}
              </Field>
            )}
          </form.Field>
        )}
        <form.Subscribe selector={(s) => s.isSubmitting}>
          {(busy) => (
            <Button type="submit" className="mt-1 h-10 w-full" disabled={busy}>
              {submit}
            </Button>
          )}
        </form.Subscribe>
      </FieldGroup>
    </form>
  );
}

export function SignInPage() {
  const { status, signIn, setPassword } = useSession();
  if (!status) return null;

  if (status.signed_in && status.bootstrap) {
    return (
      <Frame title="设置管理口令" description="这是登录面板用的口令，与 agent 使用的访问令牌无关。设置后，访问令牌不能再登录面板。">
        <SecretForm
          key="new-password"
          id="new-password"
          label="管理口令"
          hint="忘记口令时，在部署主机上执行重置命令。"
          submit="保存并进入"
          autoComplete="new-password"
          confirm
          onSubmit={(value) => setPassword(value)}
        />
      </Frame>
    );
  }

  if (!status.password_set) {
    return (
      <Frame title="首次登录" description="还没有管理口令。用配置文件里的访问令牌登录一次，随后设置管理口令。">
        <SecretForm
          key="token"
          id="token"
          label="访问令牌"
          hint="即服务配置中的 MEMORY_MCP_AUTH_TOKEN。"
          submit="继续"
          autoComplete="off"
          onSubmit={(token) => signIn({ token })}
        />
      </Frame>
    );
  }

  return (
    <Frame title="登录" description="输入管理口令，回到待审队列。">
      <SecretForm
        key="password"
        id="password"
        label="管理口令"
        hint="登录状态保留 7 天，使用时自动延长。"
        submit="登录"
        autoComplete="current-password"
        onSubmit={(password) => signIn({ password })}
      />
    </Frame>
  );
}
