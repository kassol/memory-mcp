// The recall log (issue #15): what was asked, by which token, how long it took and what came back.
// The top three results open in the memory sheet. Logging itself is a setting, shown here because
// this is where you notice it is on.
import { useQueryClient } from "@tanstack/react-query";
import { Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, Loading } from "@/components/page";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, failed } from "@/lib/api";
import { keys, useRecallLog, useSettings } from "@/lib/queries";
import { when } from "@/lib/terms";
import type { RecallLogEntry, Setting } from "@/lib/types";

const PAGE = 50;
const MAX = 200;

function LogSwitch() {
  const queryClient = useQueryClient();
  const settings = useSettings();
  const setting = settings.data?.find((s) => s.key === "recall_log_enabled");

  const save = async (value: boolean | null) => {
    try {
      const next =
        value === null
          ? await api<Setting>("/settings/recall_log_enabled", { method: "DELETE" })
          : await api<Setting>("/settings/recall_log_enabled", { method: "PUT", body: { value } });
      queryClient.setQueryData<Setting[]>(keys.settings, (old) => old?.map((x) => (x.key === next.key ? next : x)));
      toast.success(value === null ? "已恢复默认" : value ? "已开启检索记录" : "已关闭检索记录");
    } catch (error) {
      failed(error);
    }
  };

  if (!setting) return null;
  return (
    <div className="flex items-center gap-3">
      <Switch
        aria-label="记录检索"
        checked={Boolean(setting.value)}
        onCheckedChange={(checked) => void save(checked)}
      />
      <span className="text-sm">
        记录检索（{setting.value ? "开启" : "关闭"}）
        <span className="ml-2 text-xs text-muted-foreground">保留 30 天。日统计不受影响。</span>
      </span>
      {setting.source === "console" ? (
        <Button variant="ghost" size="sm" onClick={() => void save(null)}>
          恢复默认
        </Button>
      ) : null}
    </div>
  );
}

function Clear() {
  const queryClient = useQueryClient();
  const clear = async () => {
    try {
      const { deleted } = await api<{ deleted: number }>("/recall-log", { method: "DELETE" });
      void queryClient.invalidateQueries({ queryKey: ["recall-log"] });
      toast.success(`已清空 ${deleted} 条检索记录`);
    } catch (error) {
      failed(error);
    }
  };
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Trash2 />
          清空记录
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>清空检索记录？</AlertDialogTitle>
          <AlertDialogDescription>只删除检索记录，日统计（写入数、召回数、耗时）保留。此操作不能撤销。</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => void clear()}>
            清空
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function Results({ entry, onMemory }: { entry: RecallLogEntry; onMemory: (id: string) => void }) {
  if (!entry.memory_ids.length) return <span className="text-xs text-muted-foreground">无结果</span>;
  return (
    <div className="flex gap-1">
      {entry.memory_ids.map((id, i) => (
        <Button
          key={id}
          variant="ghost"
          size="sm"
          aria-label={`打开第 ${i + 1} 条结果`}
          title={id}
          onClick={() => onMemory(id)}
        >
          {i + 1}
        </Button>
      ))}
    </div>
  );
}

export function RecallLogPanel({ onMemory }: { onMemory: (id: string) => void }) {
  const [limit, setLimit] = useState(PAGE);
  const log = useRecallLog(limit);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <LogSwitch />
        <Clear />
      </div>
      {log.error && <ErrorState error={log.error} onRetry={() => void log.refetch()} />}
      {log.isPending && <Loading rows={4} />}
      {log.data && !log.data.items.length ? (
        <EmptyState icon={Search} title="还没有检索记录">
          开启记录后，每次 recall 都会出现在这里：查询、令牌、耗时与结果。
        </EmptyState>
      ) : null}
      {log.data && log.data.items.length ? (
        <>
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>查询</TableHead>
                  <TableHead className="hidden md:table-cell">令牌</TableHead>
                  <TableHead className="text-right">耗时</TableHead>
                  <TableHead className="text-right">结果</TableHead>
                  <TableHead>打开</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {log.data.items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">{when(entry.at)}</TableCell>
                    <TableCell className="max-w-64 text-sm break-all">{entry.query}</TableCell>
                    <TableCell className="hidden text-xs text-muted-foreground md:table-cell">{entry.token ?? "面板"}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground tabular-nums">{entry.latency_ms} ms</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground tabular-nums">{entry.results}</TableCell>
                    <TableCell>
                      <Results entry={entry} onMemory={onMemory} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              共 {log.data.total} 条，显示最近 {log.data.items.length} 条
            </span>
            {log.data.items.length < log.data.total && limit < MAX ? (
              <Button variant="outline" size="sm" onClick={() => setLimit((n) => Math.min(n + PAGE, MAX))}>
                加载更多
              </Button>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
