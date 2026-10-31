// Security settings: change the admin password, sign out every console session.
import { useForm } from "@tanstack/react-form";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
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
    <Card>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void form.handleSubmit();
        }}
        className="flex flex-col gap-6"
      >
        <CardHeader>
          <CardTitle>管理口令</CardTitle>
          <CardDescription>修改登录面板用的口令，需要输入当前口令。忘记口令时，在部署主机上执行重置命令。</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup className="max-w-sm">
            {field("current", "当前口令", "current-password")}
            {field("next", "新口令", "new-password")}
            {field("again", "再输入一次新口令", "new-password")}
            {error ? <FieldError>{error}</FieldError> : null}
          </FieldGroup>
        </CardContent>
        <CardFooter className="border-t">
          <form.Subscribe selector={(s) => s.isSubmitting}>
            {(busy) => (
              <Button type="submit" disabled={busy}>
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
    <Card>
      <CardHeader>
        <CardTitle>登录状态</CardTitle>
        <CardDescription>退出所有设备上的面板登录，包括当前这台。设备丢失时使用。</CardDescription>
      </CardHeader>
      <CardContent>
        <FieldDescription>访问令牌不受影响，agent 照常工作。</FieldDescription>
      </CardContent>
      <CardFooter className="border-t">
        <Button
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
    <>
      <ChangePassword />
      <SignOutEverywhere />
    </>
  );
}
