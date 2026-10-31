import { useForm } from "@tanstack/react-form";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AuthError } from "@/lib/api";
import { useSession } from "@/lib/session";

export function SignInPage() {
  const { signIn, message } = useSession();
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);

  const form = useForm({
    defaultValues: { token: "" },
    onSubmit: async ({ value, formApi }) => {
      const token = value.token.trim();
      if (!token) return;
      setError("");
      formApi.reset();
      try {
        await signIn(token);
      } catch (e) {
        setError(e instanceof AuthError ? "令牌无效，请重新输入。" : e instanceof Error ? e.message : String(e));
        input.current?.focus();
      }
    },
  });

  return (
    <main className="grid flex-1 place-items-center px-4 py-8">
      <form
        className="w-full max-w-sm"
        onSubmit={(e) => {
          e.preventDefault();
          void form.handleSubmit();
        }}
      >
        <h2 className="m-0 mb-1 text-xl font-bold">输入访问令牌</h2>
        <p className="mt-0 mb-6 text-sm text-ink-2">与服务配置中的 Bearer 令牌相同。只保存在本标签页，关闭即清除。</p>
        <label htmlFor="token" className="mb-1.5 block text-[0.8125rem] text-ink-2">
          令牌
        </label>
        <form.Field name="token">
          {(field) => (
            <Input
              ref={input}
              id="token"
              type="password"
              autoComplete="current-password"
              spellCheck={false}
              required
              value={field.state.value}
              onChange={(e) => field.handleChange(e.target.value)}
            />
          )}
        </form.Field>
        <p role="alert" className="mt-1.5 mb-3 min-h-6 text-sm text-danger">
          {error || message}
        </p>
        <form.Subscribe selector={(s) => s.isSubmitting}>
          {(busy) => (
            <Button type="submit" variant="primary" disabled={busy}>
              进入
            </Button>
          )}
        </form.Subscribe>
      </form>
    </main>
  );
}
