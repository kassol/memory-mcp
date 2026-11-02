// Refresh is the same control on every page: a quiet icon that turns while the data reloads.
import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function RefreshButton({ label, busy, onClick }: { label: string; busy: boolean; onClick: () => void }) {
  return (
    <Button variant="ghost" size="icon-sm" aria-label={label} title={label} disabled={busy} onClick={onClick}>
      <RefreshCw className={cn(busy && "animate-spin")} />
    </Button>
  );
}
