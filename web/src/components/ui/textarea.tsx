import * as React from "react"
import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "w-full min-w-0 rounded-[6px] border border-rule-strong bg-sheet px-2.5 py-2 text-[15px] text-ink outline-none placeholder:text-ink-3 hover:border-ink-3 focus-visible:border-transparent focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-blue disabled:opacity-50 aria-invalid:border-danger leading-[1.7]",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
