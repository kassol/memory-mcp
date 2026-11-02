// Command palette (Ctrl/Cmd+K): jump to a page, or search memories and open one in the records page.
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { FileText, Search } from "lucide-react";
import { useDeferredValue, useEffect, useState } from "react";

import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
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

  // cmdk keeps its own highlighted item; results that arrive after typing would leave nothing
  // highlighted, so Enter did nothing. Highlight the first visible entry whenever the list changes.
  const pages = NAV.filter((n) => !query || n.label.includes(query));
  const first = pages[0] ? `page:${pages[0].to}` : memories.data?.[0] ? `memory:${memories.data[0].memory_id}` : query ? `records:${query}` : "";
  const [picked, setPicked] = useState("");
  const [seen, setSeen] = useState(first);
  if (seen !== first) {
    setSeen(first);
    setPicked(first);
  }

  const go = (fn: () => void) => {
    onOpenChange(false);
    setText("");
    fn();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <Command shouldFilter={false} value={picked} onValueChange={setPicked}>
      <CommandInput placeholder="跳转到页面，或输入内容检索记忆" value={text} onValueChange={setText} />
      <CommandList>
        <CommandEmpty>{memories.isFetching ? "检索中…" : "没有匹配的页面或记忆"}</CommandEmpty>
        <CommandGroup heading="页面">
          {pages.map((n) => (
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
                  <span className="truncate font-mono text-xs text-muted-foreground">{m.entity_key}</span>
                  <span className="truncate">{m.content}</span>
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {query ? (
          <CommandGroup heading="检索">
            <CommandItem
              value={`records:${query}`}
              onSelect={() => go(() => void navigate({ to: "/records", search: { q: query } }))}
            >
              <Search aria-hidden />
              <span>在档案中检索「{query}」</span>
            </CommandItem>
          </CommandGroup>
        ) : null}
      </CommandList>
      <div className="flex items-center gap-3 border-t border-border/70 px-3 py-2 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> 选择</span>
        <span className="flex items-center gap-1"><Kbd>↵</Kbd> 打开</span>
        <span className="ml-auto flex items-center gap-1"><Kbd>esc</Kbd> 关闭</span>
      </div>
      </Command>
    </CommandDialog>
  );
}
