// Signed-out views: sign in with the admin password; on a fresh deployment, sign in once with the
// configuration-file access token, then set the admin password (docs/adr/0001).
import { useForm } from "@tanstack/react-form";
import { BookMarked } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSession } from "@/lib/session";

function Frame({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="flex items-center gap-2 font-medium">
        <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <BookMarked className="size-4" />
        </div>
        记忆登记簿
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">
            <h1>{title}</h1>
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
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
  const input = useRef<HTMLInputElement>(null);
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
              <Input
                ref={input}
                id={id}
                type="password"
                autoComplete={autoComplete}
                spellCheck={false}
                required
                aria-invalid={!!error}
                value={field.state.value}
                onChange={(e) => field.handleChange(e.target.value)}
              />
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
            <Button type="submit" className="w-full" disabled={busy}>
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
      <Frame title="设置管理口令" description="登录面板用的口令，与 agent 使用的访问令牌无关。设置后，访问令牌不能再登录面板。">
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
    <Frame title="登录" description="输入管理口令。">
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
