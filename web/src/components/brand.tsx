// The product mark: a graphite seal with the registry dot. Used by the shell, the sign-in page and
// the first-load view, so the identity comes from one place.
import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative grid size-8 shrink-0 place-items-center rounded-[9px] bg-foreground text-[13px] font-semibold text-background",
        className,
      )}
    >
      记
      <span className="absolute right-1 bottom-1 size-1.5 rounded-full bg-primary" />
    </span>
  );
}
