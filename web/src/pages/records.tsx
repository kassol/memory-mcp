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
import { ArrowDown, ArrowUp, ArrowUpDown, Archive, ChevronsLeft, ChevronsRight, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Highlight } from "@/components/highlight";
import { EmptyState, ErrorState, PageBody, PageHeader } from "@/components/page";
import { History, RecordCard, type EditMode } from "@/components/record-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsMobile } from "@/hooks/use-mobile";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { keys, searchMemories, useMemory } from "@/lib/queries";
import { cleanRecordsSearch, DEFAULT_SORT, SORTS, type RecordsSearch } from "@/lib/records-search";
import { RecallLogPanel } from "@/pages/recall-log";
import { shortWhen } from "@/lib/terms";
import type { MemoryItem, MemoryView } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE = 50;
const ALL = "__all";

interface ListPage {
  results: MemoryItem[];
  matched: number;
}

function SortHeader({ label, sorted, onClick }: { label: string; sorted: false | "asc" | "desc"; onClick?: (event: unknown) => void }) {
  if (!onClick) return <span>{label}</span>;
  const Icon = sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown;
  return (
    <Button variant="ghost" size="sm" className="group -ml-2.5 h-7 text-[11px] font-medium text-muted-foreground hover:text-foreground" onClick={onClick}>
      {label}
      <Icon
        className={cn(
          "size-3 transition-opacity",
          sorted ? "text-foreground" : "text-muted-foreground/50 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100",
        )}
      />
    </Button>
  );
}

function makeColumns(query: string): ColumnDef<MemoryItem>[] {
  return [
  {
    accessorKey: "entity_key",
    header: "Key",
    // Keys run long (60+ characters); cap the column so content and times stay on screen.
    cell: ({ row }) => (
      <span className="block max-w-40 truncate font-mono text-[11px] text-muted-foreground md:max-w-64" title={row.original.entity_key}>
        <Highlight text={row.original.entity_key} query={query} />
      </span>
    ),
  },
  {
    accessorKey: "content",
    header: "内容",
    enableSorting: false,
    cell: ({ row }) => (
      <span className="line-clamp-2 min-w-48 text-[13px] leading-6 whitespace-normal">
        <Highlight text={row.original.content} query={query} />
      </span>
    ),
  },
  {
    accessorKey: "created_at",
    header: "写入时间",
    cell: ({ row }) => <span className="text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">{shortWhen(row.original.created_at)}</span>,
  },
  {
    accessorKey: "valid_from",
    header: "生效时间",
    cell: ({ row }) => <span className="text-[11px] whitespace-nowrap text-muted-foreground tabular-nums">{shortWhen(row.original.valid_from)}</span>,
  },
  ];
}

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

function MobileRow({ m, query, onOpen }: { m: MemoryItem; query: string; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full flex-col gap-1.5 rounded-xl border border-border/80 bg-card p-3.5 text-left transition-colors active:bg-muted/50"
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
          <Highlight text={m.entity_key} query={query} />
        </span>
        <span className="flex shrink-0 items-center gap-1.5 pl-2 text-[10px] text-muted-foreground">
          <span className="size-1 rounded-full bg-muted-foreground/35" />
          {m.entity_type}
        </span>
      </div>
      <span className="line-clamp-2 text-[13px] leading-6">
        <Highlight text={m.content} query={query} />
      </span>
      <span className="text-[10px] text-muted-foreground tabular-nums">{shortWhen(m.created_at)}</span>
    </button>
  );
}

export function RecordsPage({
  search,
  onSearch,
}: {
  search: RecordsSearch;
  onSearch: (next: RecordsSearch, options?: { replace?: boolean }) => void;
}) {
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  // Records and the recall log share this page: both answer "what has been asked and what is known".
  const view = search.view ?? "records";
  const query = search.q ?? "";
  const type = search.type ?? "";
  const keyFilter = search.key ?? "";
  const page = search.page ?? 0;
  const sortValue = search.sort ?? DEFAULT_SORT;
  const sorting: SortingState = [{ id: sortValue.split(":")[0], desc: sortValue.endsWith(":desc") }];
  const [keyDraft, setKeyDraft] = useState(keyFilter);
  const [draft, setDraft] = useState(query);
  const searchRef = useRef<HTMLInputElement>(null);

  // The address is the source of truth; a back step or a link can change it under the drafts.
  useEffect(() => setDraft(query), [query]);
  useEffect(() => setKeyDraft(keyFilter), [keyFilter]);

  // `/` focuses the search field from anywhere on the page, as in other keyboard-first consoles.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "")) return;
      if (document.querySelector("[role=dialog], [role=alertdialog]")) return;
      event.preventDefault();
      searchRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const columns = useMemo(() => makeColumns(query), [query]);

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
  const searchQuery = useQuery({
    queryKey: keys.search(query, type),
    queryFn: () => searchMemories(query, type, 30),
    enabled: !!query,
  });

  const active = query ? searchQuery : list;
  const rows = query ? (searchQuery.data ?? []) : (list.data?.results ?? []);
  const matched = list.data?.matched ?? 0;
  const pages = Math.max(1, Math.ceil(matched / PAGE));
  // A saved link can outlive the records it pointed at; say so instead of showing an empty table.
  const beyond = !query && page > 0 && matched > 0 && page >= pages;

  // A list change drops an open record; opening or closing one keeps every filter in place.
  const navigateList = (patch: Partial<RecordsSearch>) => {
    onSearch(cleanRecordsSearch({ ...search, memory: undefined, ...patch }));
  };
  const openRecord = (id: string | null) => {
    onSearch(cleanRecordsSearch({ ...search, memory: id ?? undefined }), { replace: !id });
  };

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
      const next = typeof updater === "function" ? updater(sorting) : updater;
      const first = next[0];
      navigateList({ sort: first ? `${first.id}:${first.desc ? "desc" : "asc"}` : undefined, page: undefined });
    },
    getRowId: (row) => row.memory_id,
  });

  const changed = (next: MemoryView | null) => {
    // A correction moves the row to the new version; an archive drops it from the list.
    void queryClient.invalidateQueries({ queryKey: query ? keys.search(query, type) : keys.records });
    void queryClient.invalidateQueries({ queryKey: ["memory-types"] });
    openRecord(next ? next.memory_id : null);
  };

  const clearSearch = () => {
    setDraft("");
    navigateList({ q: undefined, page: undefined });
  };

  const clearFilters = () => {
    setKeyDraft("");
    navigateList({ key: undefined, type: undefined, page: undefined });
  };

  return (
    <>
      <PageHeader title="档案">
        {view === "records" && !query && list.data && <span className="text-sm text-muted-foreground tabular-nums">共 {matched} 条</span>}
      </PageHeader>
      <PageBody className="flex flex-col">
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          <div className="flex items-center gap-4 border-b border-border/70">
            {(["records", "log"] as const).map((v) => (
              <button
                key={v}
                onClick={() => navigateList({ view: v === "log" ? "log" : undefined, page: undefined })}
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
            <RecallLogPanel onMemory={openRecord} />
          ) : (
            <>
              <div className="flex flex-col gap-2 md:flex-row md:items-center">
                <div className="relative md:w-96">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    ref={searchRef}
                    type="search"
                    aria-label="检索"
                    placeholder="检索内容或型号，回车执行"
                    className="h-9 bg-card pr-9 pl-8"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") navigateList({ q: draft.trim() || undefined, page: undefined });
                      if (e.key === "Escape" && draft) clearSearch();
                    }}
                  />
                  {!draft ? (
                    <Kbd className="pointer-events-none absolute top-1/2 right-2 hidden -translate-y-1/2 text-[10px] text-muted-foreground md:block">/</Kbd>
                  ) : null}
                </div>
                {!query && (
                  <Input
                    aria-label="按 key 过滤"
                    placeholder="key 过滤"
                    spellCheck={false}
                    className="h-9 bg-card md:w-52"
                    value={keyDraft}
                    onChange={(e) => setKeyDraft(e.target.value)}
                    onBlur={() => navigateList({ key: keyDraft.trim() || undefined, page: undefined })}
                    onKeyDown={(e) => e.key === "Enter" && navigateList({ key: keyDraft.trim() || undefined, page: undefined })}
                  />
                )}
                <Select value={type || ALL} onValueChange={(v) => navigateList({ type: v === ALL ? undefined : v, page: undefined })}>
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
                  onValueChange={(v) => navigateList({ sort: v === DEFAULT_SORT ? undefined : v, page: undefined })}
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
                    onClick={clearSearch}
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
                beyond ? (
                  <EmptyState
                    icon={Archive}
                    title="这一页没有记录"
                    action={
                      <Button variant="outline" size="sm" onClick={() => navigateList({ page: undefined })}>
                        回到第一页
                      </Button>
                    }
                  >
                    记录变少后，这一页已经超出范围。
                  </EmptyState>
                ) : (
                <EmptyState
                  icon={query ? Search : Archive}
                  title={query ? "没有匹配的记忆" : "没有当前记忆"}
                  action={
                    query ? (
                      <Button variant="outline" size="sm" onClick={clearSearch}>清除检索</Button>
                    ) : keyFilter || type ? (
                      <Button variant="outline" size="sm" onClick={clearFilters}>清除筛选</Button>
                    ) : undefined
                  }
                >
                  {query ? "换个说法，或直接用型号、版本号检索。" : keyFilter || type ? "换一个过滤条件。" : undefined}
                </EmptyState>
                )
              ) : isMobile ? (
                <div className="flex flex-col gap-2">
                  {rows.map((row) => (
                    <MobileRow key={row.memory_id} m={row} query={query} onOpen={() => openRecord(row.memory_id)} />
                  ))}
                </div>
              ) : (
                <div className="records-table overflow-x-auto rounded-xl border border-border/80 bg-card lg:overflow-visible">
                  <Table>
                    <TableHeader className="sticky top-0 z-10 bg-card [&_th]:bg-card">
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
                              data-state={row.id === search.memory ? "selected" : undefined}
                              className="cursor-pointer border-border/60 data-[state=selected]:bg-accent/60"
                              onClick={() => openRecord(row.id)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  openRecord(row.id);
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

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>{query ? (searchQuery.data ? `最相关的 ${rows.length} 条` : "") : list.data ? `第 ${Math.min(page + 1, pages)} / ${pages} 页` : ""}</span>
                {!query && (
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon-sm" aria-label="首页" disabled={page === 0 || list.isFetching} onClick={() => navigateList({ page: undefined })}>
                      <ChevronsLeft />
                    </Button>
                    <Button variant="outline" size="sm" disabled={page === 0 || list.isFetching} onClick={() => navigateList({ page: page > 1 ? page - 1 : undefined })}>
                      上一页
                    </Button>
                    <Button variant="outline" size="sm" disabled={page + 1 >= pages || list.isFetching} onClick={() => navigateList({ page: page + 1 })}>
                      下一页
                    </Button>
                    <Button variant="ghost" size="icon-sm" aria-label="末页" disabled={page + 1 >= pages || list.isFetching} onClick={() => navigateList({ page: pages > 1 ? pages - 1 : undefined })}>
                      <ChevronsRight />
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </PageBody>

      <Sheet open={!!search.memory} onOpenChange={(open) => !open && openRecord(null)}>
        <SheetContent className="w-full gap-0 overflow-y-auto border-l-border/80 sm:max-w-2xl" style={{ maxWidth: "42rem" }}>
          <SheetHeader className="sticky top-0 z-10 border-b border-border/70 bg-background px-5 py-4">
            <SheetTitle className="text-base">记忆详情</SheetTitle>
            <SheetDescription className="text-xs">全文与版本历史，必要时改正或归档。</SheetDescription>
          </SheetHeader>
          <div className="p-5">{search.memory && <Detail key={search.memory} id={search.memory} onChanged={changed} />}</div>
        </SheetContent>
      </Sheet>
    </>
  );
}
