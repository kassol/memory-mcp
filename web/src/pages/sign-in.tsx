import { useForm } from "@tanstack/react-form";
import { BookMarked } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
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

  const shown = error || message;
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
            <h1>输入访问令牌</h1>
          </CardTitle>
          <CardDescription>与服务配置中的 Bearer 令牌相同。</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void form.handleSubmit();
            }}
          >
            <FieldGroup>
              <form.Field name="token">
                {(field) => (
                  <Field data-invalid={!!shown || undefined}>
                    <FieldLabel htmlFor="token">令牌</FieldLabel>
                    <Input
                      ref={input}
                      id="token"
                      type="password"
                      autoComplete="current-password"
                      spellCheck={false}
                      required
                      aria-invalid={!!shown}
                      value={field.state.value}
                      onChange={(e) => field.handleChange(e.target.value)}
                    />
                    {shown ? <FieldError>{shown}</FieldError> : <FieldDescription>只保存在本标签页，关闭即清除。</FieldDescription>}
                  </Field>
                )}
              </form.Field>
              <form.Subscribe selector={(s) => s.isSubmitting}>
                {(busy) => (
                  <Button type="submit" className="w-full" disabled={busy}>
                    进入
                  </Button>
                )}
              </form.Subscribe>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
