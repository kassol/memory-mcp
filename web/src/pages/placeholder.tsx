import { Construction } from "lucide-react";

import { EmptyState, PageHeader } from "@/components/page";

/** A page whose ticket has not landed yet. */
export function PlaceholderPage({ title, children }: { title: string; children: string }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState icon={Construction} title="尚未开放">
        {children}
      </EmptyState>
    </>
  );
}
