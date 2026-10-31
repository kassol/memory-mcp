// Records: browse current memories (paging, type filter, stale-first order) or search them; open one
// to read the full text and version history, and correct or archive it.
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CaseFile, EmptyRow, Ledger, Row, Rows, SkeletonRows, Workspace } from "@/components/ledger";
import { History, RecordCard, type EditMode } from "@/components/record-card";
import { Empty, ErrorNote, Skeleton } from "@/components/registry";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { keys, searchMemories, useMemory } from "@/lib/queries";
import type { MemoryItem, MemoryView } from "@/lib/types";

const PAGE = 50;

function Detail({ id, onChanged, onBack }: { id: string; onChanged: (next: MemoryView | null) => void; onBack: () => void }) {
  const memory = useMemory(id);
  const [mode, setMode] = useState<EditMode>(null);
  return (
    <CaseFile onBack={onBack}>
      {memory.error && <ErrorNote error={memory.error} onRetry={() => void memory.refetch()} />}
      {memory.isPending && (
        <>
          <Skeleton />
          <Skeleton className="w-[60%]" />
        </>
      )}
      {memory.data && (
        <>
          <div data-single className="group/records grid">
            <RecordCard r={memory.data} mode={mode} onMode={setMode} onChanged={onChanged} />
          </div>
          <History r={memory.data} />
        </>
      )}
    </CaseFile>
  );
}

export function RecordsPage({ memory, onMemory }: { memory: string | null; onMemory: (id: string | null) => void }) {
  const queryClient = useQueryClient();
  const [order, setOrder] = useState("created_at");
  const [type, setType] = useState("");
  const [typeDraft, setTypeDraft] = useState("");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  // The open memory lives in the URL (?memory=), so the command palette can link to it.
  const selected = memory;
  const setSelected = onMemory;

  const list = useInfiniteQuery({
    queryKey: keys.records(order, type),
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams({ limit: String(PAGE), offset: String(pageParam), order });
      if (type) q.set("entity_type", type);
      return api<{ results: MemoryItem[] }>(`/memories?${q}`).then((d) => d.results);
    },
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.length < PAGE ? undefined : pages.length * PAGE),
    enabled: !query,
  });
  const search = useQuery({
    queryKey: keys.search(query, type),
    queryFn: () => searchMemories(query, type, 30),
    enabled: !!query,
  });

  const active = query ? search : list;
  const items: MemoryItem[] = query ? (search.data ?? []) : (list.data?.pages.flat() ?? []);

  const changed = (next: MemoryView | null) => {
    // A correction moves the row to the new version; an archive drops it from the list.
    void queryClient.invalidateQueries({ queryKey: query ? keys.search(query, type) : ["records"] });
    if (next) setSelected(next.memory_id);
    else setSelected(null);
  };

  const head = (
    <>
      <Input
        type="search"
        aria-label="检索"
        placeholder="检索记忆（含型号、版本号）"
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
      <div className="flex items-center gap-2">
        {!query && (
          <select
            aria-label="排序"
            value={order}
            onChange={(e) => setOrder(e.target.value)}
            className="w-auto rounded-[6px] border border-rule-strong bg-sheet px-2 py-[0.3125rem] text-sm text-ink hover:border-ink-3"
          >
            <option value="created_at">最新写入在前</option>
            <option value="valid_from">最久未更新在前</option>
          </select>
        )}
        <Input
          aria-label="按类型过滤"
          placeholder="类型，如 fact"
          spellCheck={false}
          className="py-[0.3125rem] text-sm"
          value={typeDraft}
          onChange={(e) => setTypeDraft(e.target.value)}
          onBlur={() => setType(typeDraft.trim())}
          onKeyDown={(e) => e.key === "Enter" && setType(typeDraft.trim())}
        />
      </div>
    </>
  );

  const foot = (
    <>
      <span>{active.data ? (query ? `最相关的 ${items.length} 条` : `已载入 ${items.length} 条`) : ""}</span>
      {!query && list.hasNextPage && (
        <Button variant="quiet" size="sm" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
          载入更多
        </Button>
      )}
    </>
  );

  return (
    <Workspace reading={selected !== null}>
      <Ledger label="档案列表" head={head} foot={foot}>
        <Rows label="记忆">
          {active.isPending && <SkeletonRows />}
          {active.error && <li><ErrorNote error={active.error} onRetry={() => void active.refetch()} /></li>}
          {active.data && !items.length && (
            <EmptyRow>
              <strong className="mb-1 block text-base text-ink">{query ? "没有匹配的记忆" : "没有当前记忆"}</strong>
              {query && "换个说法，或直接用型号、版本号检索。"}
            </EmptyRow>
          )}
          {items.map((m, i) => (
            <Row
              key={m.memory_id}
              no={String(i + 1)}
              rowKey={m.entity_key}
              identifier
              gist={m.content}
              selected={m.memory_id === selected}
              onOpen={() => setSelected(m.memory_id)}
            />
          ))}
        </Rows>
      </Ledger>
      {selected ? (
        <Detail key={selected} id={selected} onChanged={changed} onBack={() => setSelected(null)} />
      ) : (
        <CaseFile>
          <Empty title="选一条记忆">查看全文和版本历史，必要时改正或归档。</Empty>
        </CaseFile>
      )}
    </Workspace>
  );
}
