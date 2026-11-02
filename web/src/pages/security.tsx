// Security settings: change the admin password, sign out every console session.
import { useForm } from "@tanstack/react-form";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSession } from "@/lib/session";

function ChangePassword() {
  const { setPassword } = useSession();
  const [error, setError] = useState("");
  const form = useForm({
    defaultValues: { current: "", next: "", again: "" },
    onSubmit: async ({ value, formApi }) => {
      if (!value.next) {
        setError("新口令不能为空");
        return;
      }
      if (value.next !== value.again) {
        setError("两次输入的新口令不一致");
        return;
      }
      setError("");
      try {
        await setPassword(value.next, value.current);
        formApi.reset();
        toast.success("管理口令已更新");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
  });
  const field = (name: "current" | "next" | "again", label: string, autoComplete: string) => (
    <form.Field name={name}>
      {(f) => (
        <Field>
          <FieldLabel htmlFor={`pw-${name}`}>{label}</FieldLabel>
          <Input
            id={`pw-${name}`}
            type="password"
            autoComplete={autoComplete}
            value={f.state.value}
            onChange={(e) => f.handleChange(e.target.value)}
          />
        </Field>
      )}
    </form.Field>
  );
  return (
    <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void form.handleSubmit();
        }}
        className="flex flex-col gap-0"
      >
        <CardHeader className="border-b border-border/70 px-5 py-4">
          <CardTitle className="text-[13px] font-medium">管理口令</CardTitle>
        </CardHeader>
        <CardContent className="px-5 py-5">
          <FieldGroup className="max-w-sm">
            {field("current", "当前口令", "current-password")}
            {field("next", "新口令", "new-password")}
            {field("again", "再输入一次新口令", "new-password")}
            {error ? <FieldError>{error}</FieldError> : null}
          </FieldGroup>
        </CardContent>
        <CardFooter className="border-t border-border/70 px-5 py-3">
          <form.Subscribe selector={(s) => s.isSubmitting}>
            {(busy) => (
              <Button type="submit" size="sm" disabled={busy}>
                更新口令
              </Button>
            )}
          </form.Subscribe>
        </CardFooter>
      </form>
    </Card>
  );
}

function SignOutEverywhere() {
  const { signOutEverywhere } = useSession();
  const [busy, setBusy] = useState(false);
  return (
    <Card className="gap-0 rounded-xl border border-border/80 py-0 shadow-none ring-0">
      <CardHeader className="border-b border-border/70 px-5 py-4">
        <CardTitle className="text-[13px] font-medium">登录状态</CardTitle>
      </CardHeader>
      <CardContent className="px-5 py-5">
        <FieldDescription>访问令牌不受影响，agent 照常工作。</FieldDescription>
      </CardContent>
      <CardFooter className="border-t border-border/70 px-5 py-3">
        <Button
          size="sm"
          variant="destructive"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await signOutEverywhere();
            } catch (e) {
              toast.error(e instanceof Error ? e.message : String(e));
              setBusy(false);
            }
          }}
        >
          退出所有设备
        </Button>
      </CardFooter>
    </Card>
  );
}

export function SecuritySection() {
  return (
    <div className="flex flex-col gap-4">
      <ChangePassword />
      <SignOutEverywhere />
    </div>
  );
}
