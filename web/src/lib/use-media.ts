import { useSyncExternalStore } from "react";

/** Wide enough for the ledger and the case file side by side (Tailwind `md`). */
export function useWide() {
  const query = "(min-width: 768px)";
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
  );
}
