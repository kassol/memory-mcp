// Records: current memories as a table (TanStack Table, server-side sorting and paging), filtered by
// key and type, or a search; a row opens the memory in a sheet with its version history.
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, Archive, Search, X } from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorState, PageBody, PageHeader } from "@/components/page";
import { History, RecordCard, type EditMode } from "@/components/record-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsMobile } from "@/hooks/use-mobile";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { keys, searchMemories, useMemory } from "@/lib/queries";
import { RecallLogPanel } from "@/pages/recall-log";
import { when } from "@/lib/terms";
import type { MemoryItem, MemoryView } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE = 50;
const ALL = "__all";

const SORTS = [
  { value: "created_at:desc", label: "最新写入" },
  { value: "created_at:asc", label: "最早写入" },
  { value: "valid_from:asc", label: "最久未更新" },
  { value: "valid_from:desc", label: "最近更新" },
  { value: "entity_key:asc", label: "Key A–Z" },
];

interface ListPage {
  results: MemoryItem[];
  matched: number;
}

function SortHeader({ label, sorted, onClick }: { label: string; sorted: false | "asc" | "desc"; onClick?: (event: unknown) => void }) {
  if (!onClick) return <span>{label}</span>;
  const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown;
  return (
    <Button variant="ghost" size="sm" className="-ml-2.5 h-7 text-[11px] font-medium text-muted-foreground hover:text-foreground" onClick={onClick}>
      {label}
      <Icon className={cn("size-3", sorted ? "text-foreground" : "text-muted-foreground/60")} />
    </Button>
  );
}

const columns: ColumnDef<MemoryItem>[] = [
  {
    accessorKey: "entity_key",
    header: "Key",
    // Keys run long (60+ characters); cap the column so content and times stay on screen.
    cell: ({ row }) => (
      <span className="block max-w-40 truncate font-mono text-[11px] text-muted-foreground md:max-w-64" title={row.original.entity_key}>
        {row.original.entity_key}
      </span>
    ),
  },
  {
    accessorKey: "entity_type",
    header: "类型",
    cell: ({ row }) => (
      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span className="size-1 rounded-full bg-muted-foreground/35" />
        {row.original.entity_type}
      </span>
    ),
  },
  {
    accessorKey: "content",
    header: "内容",
    enableSorting: false,
    cell: ({ row }) => <span className="line-clamp-2 min-w-48 text-[13px] leading-6 whitespace-normal">{row.original.content}</span>,
  },
  {
    accessorKey: "created_at",
    header: "写入时间",
    cell: ({ row }) => <span className="text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">{when(row.original.created_at)}</span>,
  },
  {
    accessorKey: "valid_from",
    header: "生效时间",
    cell: ({ row }) => <span className="text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">{when(row.original.valid_from)}</span>,
  },
];

function Detail({ id, onChanged }: { id: string; onChanged: (next: MemoryView | null) => void }) {
  const memory = useMemory(id);
  const [mode, setMode] = useState<EditMode>(null);
  if (memory.error) return <ErrorState error={memory.error} onRetry={() => void memory.refetch()} />;
  if (!memory.data) return <Skeleton className="h-56 w-full rounded-xl" />;
  return (
    <div className="flex flex-col gap-7">
      <RecordCard r={memory.data} mode={mode} onMode={setMode} onChanged={onChanged} />
      <History r={memory.data} />
    </div>
  );
}

function MobileRow({ m, onOpen }: { m: MemoryItem; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full flex-col gap-1.5 rounded-xl border border-border/80 bg-card p-3.5 text-left transition-colors active:bg-muted/50"
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">{m.entity_key}</span>
        <span className="flex shrink-0 items-center gap-1.5 pl-2 text-[10px] text-muted-foreground">
          <span className="size-1 rounded-full bg-muted-foreground/35" />
          {m.entity_type}
        </span>
      </div>
      <span className="line-clamp-2 text-[13px] leading-6">{m.content}</span>
      <span className="text-[10px] text-muted-foreground tabular-nums">{when(m.created_at)}</span>
    </button>
  );
}

export function RecordsPage({ memory, onMemory }: { memory: string | null; onMemory: (id: string | null) => void }) {
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);
  const [page, setPage] = useState(0);
  const [type, setType] = useState("");
  const [keyFilter, setKeyFilter] = useState("");
  const [keyDraft, setKeyDraft] = useState("");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  // Records and the recall log share this page: both answer "what has been asked and what is known".
  const [view, setView] = useState<"records" | "log">("records");

  const types = useQuery({
    queryKey: ["memory-types"],
    queryFn: () => api<{ items: { entity_type: string; count: number }[] }>("/memories/types").then((d) => d.items),
  });

  const sort = sorting[0];
  const list = useQuery({
    queryKey: [...keys.records, sort?.id, sort?.desc, type, keyFilter, page],
    queryFn: () => {
      const q = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
      if (sort) {
        q.set("sort", sort.id);
        q.set("direction", sort.desc ? "desc" : "asc");
      }
      if (type) q.set("entity_type", type);
      if (keyFilter) q.set("key", keyFilter);
      return api<ListPage>(`/memories?${q}`);
    },
    placeholderData: keepPreviousData,
    enabled: !query,
  });
  const search = useQuery({
    queryKey: keys.search(query, type),
    queryFn: () => searchMemories(query, type, 30),
    enabled: !!query,
  });

  const active = query ? search : list;
  const rows = query ? (search.data ?? []) : (list.data?.results ?? []);
  const matched = list.data?.matched ?? 0;
  const pages = Math.max(1, Math.ceil(matched / PAGE));

  // Server-side sorting and paging: the table renders one page and reports sort changes.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableSorting: !query,
    enableSortingRemoval: false,
    sortDescFirst: false,
    // Phones use a card list instead of the table.
    state: { sorting, columnVisibility: { created_at: !isMobile, valid_from: !isMobile } },
    onSortingChange: (updater) => {
      setSorting(updater);
      setPage(0);
    },
    getRowId: (row) => row.memory_id,
  });

  const changed = (next: MemoryView | null) => {
    // A correction moves the row to the new version; an archive drops it from the list.
    void queryClient.invalidateQueries({ queryKey: query ? keys.search(query, type) : keys.records });
    void queryClient.invalidateQueries({ queryKey: ["memory-types"] });
    onMemory(next ? next.memory_id : null);
  };

  const resetPage = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(0);
  };

  const clearFilters = () => {
    setKeyDraft("");
    setKeyFilter("");
    setType("");
    setPage(0);
  };

  return (
    <>
      <PageHeader title="档案" description="当前记忆、版本历史与检索记录。">
        {view === "records" && !query && list.data && <span className="text-sm text-muted-foreground tabular-nums">共 {matched} 条</span>}
      </PageHeader>
      <PageBody className="flex flex-col">
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          <div className="flex items-center gap-4 border-b border-border/70">
            {(["records", "log"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={cn(
                  "-mb-px border-b-2 pb-2 text-[13px] transition-colors",
                  view === v ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {v === "records" ? "档案" : "检索记录"}
              </button>
            ))}
          </div>
          {view === "log" ? (
            <RecallLogPanel onMemory={onMemory} />
          ) : (
            <>
              <div className="flex flex-col gap-2 md:flex-row md:items-center">
                <div className="relative md:w-96">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="search"
                    aria-label="检索"
                    placeholder="检索记忆（含型号、版本号），回车执行"
                    className="h-9 bg-card pl-8"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setQuery(draft.trim());
                      if (e.key === "Escape" && draft) {
                        setDraft("");
                        setQuery("");
                      }
                    }}
                  />
                </div>
                {!query && (
                  <Input
                    aria-label="按 key 过滤"
                    placeholder="按 key 过滤"
                    spellCheck={false}
                    className="h-9 bg-card md:w-52"
                    value={keyDraft}
                    onChange={(e) => setKeyDraft(e.target.value)}
                    onBlur={() => resetPage(setKeyFilter)(keyDraft.trim())}
                    onKeyDown={(e) => e.key === "Enter" && resetPage(setKeyFilter)(keyDraft.trim())}
                  />
                )}
                <Select value={type || ALL} onValueChange={(v) => resetPage(setType)(v === ALL ? "" : v)}>
                  <SelectTrigger aria-label="按类型过滤" className="h-9 w-full bg-card md:w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>全部类型</SelectItem>
                    {types.data?.map((t) => (
                      <SelectItem key={t.entity_type} value={t.entity_type}>
                        {t.entity_type}（{t.count}）
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={sort ? `${sort.id}:${sort.desc ? "desc" : "asc"}` : "created_at:desc"}
                  onValueChange={(v) => {
                    const [id, direction] = v.split(":");
                    setSorting([{ id, desc: direction === "desc" }]);
                    setPage(0);
                  }}
                >
                  <SelectTrigger aria-label="排序" className="h-9 w-full bg-card md:hidden">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SORTS.map((s) => (
                      <SelectItem key={s.value} value={s.value}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {query && (
                  <Button
                    variant="ghost"
                    className="text-muted-foreground"
                    onClick={() => {
                      setDraft("");
                      setQuery("");
                    }}
                  >
                    <X />
                    清除检索
                  </Button>
                )}
                {!query && (keyFilter || type) && (
                  <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={clearFilters}>
                    <X />
                    清除筛选
                  </Button>
                )}
              </div>

              {active.error && <ErrorState error={active.error} onRetry={() => void active.refetch()} />}
              {active.data && !rows.length ? (
                <EmptyState icon={query ? Search : Archive} title={query ? "没有匹配的记忆" : "没有当前记忆"}>
                  {query ? "换个说法，或直接用型号、版本号检索。" : keyFilter || type ? "换一个过滤条件。" : undefined}
                </EmptyState>
              ) : isMobile ? (
                <div className="flex flex-col gap-2">
                  {rows.map((row) => (
                    <MobileRow key={row.memory_id} m={row} onOpen={() => onMemory(row.memory_id)} />
                  ))}
                </div>
              ) : (
                <div className="records-table overflow-x-auto rounded-xl border border-border/80 bg-card lg:overflow-visible">
                  <Table>
                    <TableHeader className="sticky top-0 z-10 bg-card">
                      {table.getHeaderGroups().map((group) => (
                        <TableRow key={group.id} className="border-border/70 hover:bg-transparent">
                          {group.headers.map((header) => (
                            <TableHead
                              key={header.id}
                              className="h-9 px-3 text-[11px] font-medium text-muted-foreground"
                              aria-sort={header.column.getIsSorted() ? (header.column.getIsSorted() === "asc" ? "ascending" : "descending") : undefined}
                            >
                              <SortHeader
                                label={String(header.column.columnDef.header)}
                                sorted={header.column.getIsSorted()}
                                onClick={header.column.getCanSort() ? header.column.getToggleSortingHandler() : undefined}
                              />
                            </TableHead>
                          ))}
                        </TableRow>
                      ))}
                    </TableHeader>
                    <TableBody>
                      {active.isPending
                        ? Array.from({ length: 6 }, (_, i) => (
                            <TableRow key={i} className="border-border/60">
                              <TableCell colSpan={table.getVisibleLeafColumns().length}>
                                <Skeleton className="h-6 w-full" />
                              </TableCell>
                            </TableRow>
                          ))
                        : table.getRowModel().rows.map((row) => (
                            <TableRow
                              key={row.id}
                              tabIndex={0}
                              data-state={row.id === memory ? "selected" : undefined}
                              className="cursor-pointer border-border/60 data-[state=selected]:bg-accent/60"
                              onClick={() => onMemory(row.id)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  onMemory(row.id);
                                }
                              }}
                            >
                              {row.getVisibleCells().map((cell) => (
                                <TableCell key={cell.id} className="px-3 py-2.5 align-top">
                                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{query ? (search.data ? `最相关的 ${rows.length} 条` : "") : list.data ? `第 ${page + 1} / ${pages} 页` : ""}</span>
                {!query && (
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={page === 0 || list.isFetching} onClick={() => setPage((p) => p - 1)}>
                      上一页
                    </Button>
                    <Button variant="outline" size="sm" disabled={page + 1 >= pages || list.isFetching} onClick={() => setPage((p) => p + 1)}>
                      下一页
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </PageBody>

      <Sheet open={!!memory} onOpenChange={(open) => !open && onMemory(null)}>
        <SheetContent className="w-full gap-0 overflow-y-auto border-l-border/80 sm:max-w-2xl">
          <SheetHeader className="sticky top-0 z-10 border-b border-border/70 bg-background px-5 py-4">
            <SheetTitle className="text-base">记忆详情</SheetTitle>
            <SheetDescription className="text-xs">全文与版本历史，必要时改正或归档。</SheetDescription>
          </SheetHeader>
          <div className="p-5">{memory && <Detail key={memory} id={memory} onChanged={changed} />}</div>
        </SheetContent>
      </Sheet>
    </>
  );
}
