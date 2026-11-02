// Route-level failure states. Kept out of router.tsx so that file only builds the route tree.
import { Link } from "@tanstack/react-router";
import { Inbox } from "lucide-react";

import { EmptyState, ErrorState, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";

export function RouteError({ error, reset }: { error: unknown; reset: () => void }) {
  const shown = error instanceof Error ? error : new Error(String(error));
  return (
    <div className="p-4 md:p-8">
      <ErrorState error={shown} onRetry={reset} />
    </div>
  );
}

export function NotFound() {
  return (
    <>
      <PageHeader title="页面不存在" />
      <div className="flex min-h-0 flex-1 items-center justify-center p-8">
        <EmptyState
          icon={Inbox}
          title="没有这个页面"
          action={
            <Button asChild size="sm" variant="outline">
              <Link to="/docket">回到待审</Link>
            </Button>
          }
        />
      </div>
    </>
  );
}
