import * as React from "react"
import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "w-full min-w-0 rounded-[6px] border border-rule-strong bg-sheet px-2.5 py-2 text-[15px] text-ink outline-none placeholder:text-ink-3 hover:border-ink-3 focus-visible:border-transparent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-blue disabled:opacity-50 aria-invalid:border-danger",
        className
      )}
      {...props}
    />
  )
}

export { Input }
