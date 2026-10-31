import { Empty } from "@/components/registry";

/** A page whose ticket has not landed yet. */
export function PlaceholderPage({ title, children }: { title: string; children: string }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 pt-6 md:px-8">
        <h1 className="m-0 text-xl font-bold">{title}</h1>
        <Empty title="尚未开放">{children}</Empty>
      </div>
    </div>
  );
}
