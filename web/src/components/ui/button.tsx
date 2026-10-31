import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

// Registry buttons (DESIGN.md): one primary per decision point, secondary and quiet for the rest.
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[6px] border border-transparent font-[550] whitespace-nowrap transition-[background-color,border-color,color] duration-150 ease-out disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary: "bg-blue text-blue-ink hover:bg-[color-mix(in_oklch,var(--blue)_88%,var(--ink))]",
        secondary: "border-rule-strong bg-sheet text-ink hover:border-ink-3",
        quiet: "bg-transparent text-ink-2 hover:bg-ground hover:text-ink",
        danger: "bg-transparent text-danger hover:bg-ground",
      },
      size: {
        default: "px-3.5 py-[0.4375rem] text-[15px] leading-normal",
        sm: "px-2.5 py-1 text-sm",
        icon: "size-9",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  }
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  type = "button",
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      type={asChild ? undefined : type}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export { Button, buttonVariants }
