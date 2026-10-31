import { Toaster as Sonner, type ToasterProps } from "sonner"

// Registry toast (DESIGN.md): ink background with sheet text; errors on the archive red fill.
// Follows the system scheme through the CSS variables, so no theme prop is needed.
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      className="toaster group"
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "flex items-center gap-2 rounded-[6px] bg-ink px-3.5 py-2 text-sm text-sheet shadow-[0_6px_20px_oklch(0%_0_0/0.18)] max-w-[calc(100vw-2rem)]",
          error: "!bg-danger-fill !text-[oklch(99%_0_0)]",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
