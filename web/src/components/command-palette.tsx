// Command palette (Ctrl/Cmd+K): jump to a page, or search memories and open one in the records page.
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { FileText } from "lucide-react";
import { useDeferredValue, useEffect, useState } from "react";

import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { searchMemories } from "@/lib/queries";
import { NAV } from "@/nav";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const query = useDeferredValue(text.trim());

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const memories = useQuery({
    queryKey: ["palette", query],
    queryFn: () => searchMemories(query, "", 8),
    enabled: open && query.length > 1,
    staleTime: 30_000,
  });

  const go = (fn: () => void) => {
    onOpenChange(false);
    setText("");
    fn();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} shouldFilter={false} className="top-[20%] translate-y-0 sm:max-w-xl">
      <CommandInput placeholder="跳转到页面，或输入内容检索记忆" value={text} onValueChange={setText} />
      <CommandList>
        <CommandEmpty>{memories.isFetching ? "检索中…" : "没有匹配的页面或记忆"}</CommandEmpty>
        <CommandGroup heading="页面">
          {NAV.filter((n) => !query || n.label.includes(query)).map((n) => (
            <CommandItem key={n.to} value={`page:${n.to}`} onSelect={() => go(() => void navigate({ to: n.to }))}>
              <n.icon aria-hidden />
              {n.label}
            </CommandItem>
          ))}
        </CommandGroup>
        {!!memories.data?.length && (
          <CommandGroup heading="记忆">
            {memories.data.map((m) => (
              <CommandItem
                key={m.memory_id}
                value={`memory:${m.memory_id}`}
                onSelect={() => go(() => void navigate({ to: "/records", search: { memory: m.memory_id } }))}
              >
                <FileText aria-hidden />
                <span className="grid min-w-0">
                  <span className="truncate font-mono text-xs text-ink-2">{m.entity_key}</span>
                  <span className="truncate">{m.content}</span>
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
