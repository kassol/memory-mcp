# Memory MCP M6 上线（迁移与切换）Runbook

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to drive this runbook. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **运维 Runbook 性质**：本 plan 不直接执行任何线上动作。Sir 自己 ssh 执行；助手仅在 Sir 明确指令时代为执行。所有"VERIFY before proceed"步骤必须断言通过后再进入下一步；任何一步失败立即跳到 Task 13（Rollback）。

**Goal:** 把生产 `memory-mcp` 从 v1（LanceDB-only / JSON graph）平稳切换到 v2（SQLite 主 + LanceDB 副 + Web UI + Worker），完成数据破坏性迁移并灰度观察 24h。

**Architecture:** M1-M5 已交付 v2 完整代码、Web UI build 产物、`migrate_v1_to_v2.py` 脚本、release-tag。M6 只做线上备份 → 停服 → 拉新版 → 跑迁移 → 启新版 → 冒烟 → 灰度 → 全量切换 → 收尾，不引入新代码。

**Spec:** `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md`（§9 迁移、§11 M6、§13 风险、§14 安全）

**SLA：** 计划停服窗口 ~10 分钟（仅 backup + migration）；灰度观察 24h；rollback 路径 10 分钟内可完成。

---

## 占位符约定

所有命令中的以下名称为占位符，Sir 执行时替换为真实值；plan / repo / commit 永不出现真实值。

| 占位符 | 含义 |
|---|---|
| `<DEPLOY_HOST>` | 生产部署主机 SSH 别名（建议在 `~/.ssh/config` 配） |
| `<DEPLOY_DIR>` | 部署主机上仓库的绝对路径，默认 `~/memory-mcp`（plan 文本沿用 `~/memory-mcp` 字面值；Sir 实际部署位置不同时通读替换） |
| `<MEMORY_MCP_HOST>` | 对外服务域名（不含协议） |
| `<MEMORY_MCP_AUTH_TOKEN>` | 服务端 Bearer token（注入容器与本地 CLI 共用） |
| `<MEMORY_MCP_SESSION_SECRET>` | Web UI cookie session 签名密钥（M5 新增） |
| `<CLOUDFLARE_TUNNEL_TOKEN>` | cloudflared 隧道 token |
| `<V1_TAG>` | 当前生产对应的最后一个 v1 release tag（rollback 用） |
| `<MIGRATION_TS>` | 备份时间戳，由 `date +%F-%H%M` 生成，例 `2026-05-22-0930` |

---

## File Structure

M6 不新增 production 代码文件。本次会修改/创建的文档与 release artifact：

| File | Action | 说明 |
|------|--------|------|
| `docs/releases/v2.0.0.md` | Create | Release note：v2 范围 / 破坏性变更 / migration 命令 / rollback 步骤 |
| `AGENTS.md` | Modify | 变更日志追加 v2 production cutover 条目 |
| `<git tag> v2.0.0` | Create (local) | 由 Sir 决定何时 push origin |

线上侧文件（不入 repo）：

| Path | 说明 |
|------|------|
| `~/memory-mcp/backups/v1-data-<MIGRATION_TS>.tgz` | 迁移前完整 backup（data/ + .env） |
| `~/memory-mcp/backups/v1-data-<MIGRATION_TS>.tgz.sha256` | backup 完整性校验 |

---

## Chunk 1：Pre-flight Checklist（本地，可在窗口前几天完成）

### Task 1：仓库与代码状态确认

**Files：**
- Read only：`src/`, `tests/`, `cli/`, `web/`, `Dockerfile`, `docker-compose.yml`

- [ ] **Step 1：切到 main 并同步**

```bash
cd /Users/kassol/Workspace/memory-mcp
git fetch origin
git checkout main
git pull --ff-only origin main
git status
```

VERIFY before proceed：`git status` 显示 `nothing to commit, working tree clean`，且 `git log --oneline -1` 是 M5 收尾 commit。

- [ ] **Step 2：跑全量 Python 测试**

```bash
cd /Users/kassol/Workspace/memory-mcp
pytest -v
```

VERIFY before proceed：所有 pytest（spec §10 baseline 目标 200+）全绿，无 ERROR / FAILED。

- [ ] **Step 3：跑全量 CLI 测试**

```bash
cd /Users/kassol/Workspace/memory-mcp/cli
pytest tests/ -v
```

VERIFY before proceed：CLI 测试全绿。

- [ ] **Step 4：跑 Web UI build（验证 vite build 不爆）**

```bash
cd /Users/kassol/Workspace/memory-mcp/web
pnpm install --frozen-lockfile
pnpm build
ls -la dist/index.html dist/assets/
```

VERIFY before proceed：`dist/index.html` 与 `dist/assets/*.js`/`*.css` 都存在，build 退出码 0。

- [ ] **Step 5：本地 docker compose build 试跑**

```bash
cd /Users/kassol/Workspace/memory-mcp
docker compose build memory-mcp
```

VERIFY before proceed：multi-stage build 成功，最终镜像列表里有 `memory-mcp:latest`。

### Task 2：Migration 脚本在 dev fixture 上 dry-run + verify

**Files：**
- Read only：`tests/fixtures/v1_data/`
- Run only：`src/memory_mcp/scripts/migrate_v1_to_v2.py`

- [ ] **Step 1：准备 dev fixture 沙盒**

```bash
cd /Users/kassol/Workspace/memory-mcp
rm -rf /tmp/mem-m6-fixture-src /tmp/mem-m6-fixture-dst
cp -r tests/fixtures/v1_data /tmp/mem-m6-fixture-src
mkdir -p /tmp/mem-m6-fixture-dst
```

VERIFY before proceed：`ls /tmp/mem-m6-fixture-src` 显示 `vectors/`, `graph/` 等 v1 结构。

- [ ] **Step 2：dry-run（只统计不写）**

```bash
cd /Users/kassol/Workspace/memory-mcp
python -m memory_mcp.scripts.migrate_v1_to_v2 \
    --src /tmp/mem-m6-fixture-src \
    --dst /tmp/mem-m6-fixture-dst \
    --dry-run
```

VERIFY before proceed：输出含 `memories count: N` / `entities count: M` / `relations count: K`；退出码 0；`/tmp/mem-m6-fixture-dst` 仍为空目录。

- [ ] **Step 3：真实写 + verify**

```bash
cd /Users/kassol/Workspace/memory-mcp
python -m memory_mcp.scripts.migrate_v1_to_v2 \
    --src /tmp/mem-m6-fixture-src \
    --dst /tmp/mem-m6-fixture-dst \
    --verify
```

VERIFY before proceed：输出末尾含 `[verify] count(memories) == v1_count: OK` / `[verify] FK consistency: OK` / `[verify] LanceDB vectors aligned: OK` / `[verify] FTS5 rows == memories rows: OK`；退出码 0。

- [ ] **Step 4：清理 fixture 沙盒**

```bash
rm -rf /tmp/mem-m6-fixture-src /tmp/mem-m6-fixture-dst
```

### Task 3：环境变量与 secret 清单核对

**Files：**
- Read only：`.env.example`, `docker-compose.yml`

- [ ] **Step 1：列出 v2 所需 env 清单**

```bash
cd /Users/kassol/Workspace/memory-mcp
grep -E '^\s*-?\s*MEMORY_MCP_|^\s*-?\s*OPENROUTER_|^\s*-?\s*CLOUDFLARE_' .env.example docker-compose.yml | sort -u
```

VERIFY before proceed：清单至少包含 `MEMORY_MCP_AUTH_TOKEN` / `MEMORY_MCP_OPENROUTER_API_KEY` / `MEMORY_MCP_SESSION_SECRET` / `MEMORY_MCP_VECTOR_BACKEND` / `CLOUDFLARE_TUNNEL_TOKEN`（其余按 spec §14 注入）。

- [ ] **Step 2：本地 grep 确认无 token 泄露入仓**

```bash
cd /Users/kassol/Workspace/memory-mcp
git ls-files | xargs grep -lE '(sk-|hf_|cfd_|nrk_|gh[pousr]_)[A-Za-z0-9]{20,}' 2>/dev/null
git ls-files | xargs grep -l '<MEMORY_MCP_AUTH_TOKEN>' 2>/dev/null
```

VERIFY before proceed：第一条无输出（无真实 token 模式）；第二条若有输出仅限文档示例（占位符本身允许出现）。

### Task 4：写 release note 与打 tag（本地，不 push）

**Files：**
- Create：`docs/releases/v2.0.0.md`

- [ ] **Step 1：创建 release notes 目录**

```bash
cd /Users/kassol/Workspace/memory-mcp
mkdir -p docs/releases
ls docs/releases
```

VERIFY before proceed：目录创建成功。

- [ ] **Step 2：写 release note**

创建 `docs/releases/v2.0.0.md`，内容如下：

```markdown
# v2.0.0 — Agent Kernel

发布日期：YYYY-MM-DD（Sir 执行 cutover 当日填入）

## 范围
- 存储：SQLite 主 + LanceDB 副（只存 `(id, vector)`），FTS5 全文索引（jieba 分词）
- Schema v2：α/β/γ/δ/ε 五组新字段（review_status / origin_client / source_thread_id+refs / access_count+reinforce_count / title）
- Memory CRUD by id + Memory Merge
- Hybrid Search（vector + FTS5 + graph + reinforce + 时间衰减，RRF k=60 融合）
- Threads 完整归档（claude-code adapter，codex/chatwise 按 fixture 接入）
- 本地 CLI sync 推送 + stop hook 双步推送（threads/incremental + extract）
- Web UI 治理台（React 19 + TS 6 + Vite 8 + Tailwind v4 + shadcn）
- Background Worker（同进程 asyncio + APScheduler + SQLite 队列）
- Web UI cookie session 鉴权（Bearer 同时保留，MCP/REST/CLI 不变）

## 破坏性变更
- 数据 schema 从 v1（LanceDB-only + JSON graph）一次性迁移到 v2（SQLite + LanceDB）
- `evolution_chains.json` 表废弃（parent_id 已能完整追溯）
- 必须执行 `migrate_v1_to_v2.py` 才能启动 v2

## 新增环境变量
- `MEMORY_MCP_SESSION_SECRET`：Web UI cookie session 签名密钥（必填）
- 可选：`MEMORY_MCP_RRF_K` / `MEMORY_MCP_DECAY_LAMBDA` / `MEMORY_MCP_RECALL_DEPTH`

## Migration 命令
完整命令见 `docs/superpowers/plans/2026-05-21-memory-mcp-m6-deploy-cutover.md` Task 8。

## Rollback 步骤
完整命令见同 plan Task 13。10 分钟内可回到 v1。
```

- [ ] **Step 3：commit release note**

```bash
cd /Users/kassol/Workspace/memory-mcp
git add docs/releases/v2.0.0.md
git commit -m "docs: add v2.0.0 release notes"
```

VERIFY before proceed：`git log --oneline -1` 显示该 commit；`git status` 干净。

- [ ] **Step 4：本地打 tag（不 push，等 Sir 指令）**

```bash
cd /Users/kassol/Workspace/memory-mcp
git tag -a v2.0.0 -m "Agent Kernel: SQLite+LanceDB, hybrid search, threads, web UI, worker"
git tag --list 'v2*'
git show v2.0.0 --stat | head -30
```

VERIFY before proceed：`v2.0.0` 出现在 tag list；`git show v2.0.0` 指向上一步的 release note commit。

**Sir 决定 push 时机**：
```bash
# Sir 执行
git push origin v2.0.0
```

不要自动执行 push；助手仅在 Sir 明确说"push tag"后执行。

---

## Chunk 2：生产上线窗口（约 10 分钟停服）

> 进入本 chunk 前：Sir 已 push v2.0.0 tag，已通知相关用户即将进入计划停服窗口。

### Task 5：远程主机连通性与现状确认

**Files：** 无（远程执行）

- [ ] **Step 1：ssh 连通**

```bash
ssh <DEPLOY_HOST> 'hostname && uname -a && date'
```

VERIFY before proceed：返回主机名 / 内核信息 / 时间，无认证失败。

- [ ] **Step 2：项目目录与当前版本**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && pwd && git log --oneline -3 && git tag --points-at HEAD'
```

VERIFY before proceed：`pwd` 是 `/home/.../memory-mcp` 一类路径；`git log` 显示当前 HEAD 在 v1 release commit；记录 `<V1_TAG>`（rollback 用）。

- [ ] **Step 3：当前服务健康**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose ps'
curl -fs https://<MEMORY_MCP_HOST>/health | jq
```

VERIFY before proceed：`docker compose ps` 显示容器 `healthy`；`/health` 返回 `{"status":"ok", "vector_backend":"lancedb", ...}`。

### Task 6：生产备份（data + .env，含完整性校验）

**Files：** 无（远程执行）

- [ ] **Step 1：准备 backup 目录**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && mkdir -p backups && ls -la backups'
```

VERIFY before proceed：`backups/` 目录存在且可写。

- [ ] **Step 2：生成时间戳并打包**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  TS=$(date +%F-%H%M) && \
  echo "MIGRATION_TS=$TS" > backups/.current_ts && \
  tar -czf "backups/v1-data-$TS.tgz" data/ .env && \
  ls -lh "backups/v1-data-$TS.tgz"'
```

VERIFY before proceed：tar 文件存在、大小合理（典型 v1 数据 MB 级别）；记下 `<MIGRATION_TS>`。

- [ ] **Step 3：验证 backup 可读**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  TS=$(cat backups/.current_ts | cut -d= -f2) && \
  tar -tzf "backups/v1-data-$TS.tgz" | head -30 && \
  tar -tzf "backups/v1-data-$TS.tgz" | wc -l'
```

VERIFY before proceed：头部 30 项含 `data/vectors/`, `data/graph/`, `.env`；总行数 > 10。

- [ ] **Step 4：sha256 备案**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  TS=$(cat backups/.current_ts | cut -d= -f2) && \
  sha256sum "backups/v1-data-$TS.tgz" | tee "backups/v1-data-$TS.tgz.sha256"'
```

VERIFY before proceed：输出形如 `<64-hex>  backups/v1-data-<TS>.tgz`；`.sha256` 文件已写。

- [ ] **Step 5：本地拉一份 backup 离线兜底（可选但强烈推荐）**

```bash
mkdir -p ~/Workspace/memory-mcp-backups
scp <DEPLOY_HOST>:~/memory-mcp/backups/v1-data-<MIGRATION_TS>.tgz \
    <DEPLOY_HOST>:~/memory-mcp/backups/v1-data-<MIGRATION_TS>.tgz.sha256 \
    ~/Workspace/memory-mcp-backups/
cd ~/Workspace/memory-mcp-backups && shasum -a 256 -c v1-data-<MIGRATION_TS>.tgz.sha256
```

VERIFY before proceed：`shasum -c` 显示 `OK`；远端与本地双备份同 hash。

### Task 7：停服

**Files：** 无（远程执行）

- [ ] **Step 1：停止容器栈**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose down'
```

VERIFY before proceed：输出含 `Removed` 对应 `memory-mcp` / `cloudflared` 容器；`docker compose ps` 显示无容器在跑。

- [ ] **Step 2：确认对外服务下线**

```bash
curl -fs -o /dev/null -w '%{http_code}\n' https://<MEMORY_MCP_HOST>/health || echo 'OFFLINE'
```

VERIFY before proceed：返回 5xx / 连接拒绝 / `OFFLINE`（cloudflared tunnel offline）。**这里允许失败**，正是预期。

### Task 8：拉新版 → 构建 → 跑迁移（最关键）

**Files：** 无（远程执行）

- [ ] **Step 1：拉取所有 tag**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && git fetch origin --tags && git tag --list "v2*"'
```

VERIFY before proceed：tag 列表含 `v2.0.0`。

- [ ] **Step 2：checkout v2.0.0**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && git checkout v2.0.0 && git log --oneline -5'
```

VERIFY before proceed：HEAD 处于 detached 状态、指向 `v2.0.0`；`git log` 前几条对应 M5 收尾 commit。

- [ ] **Step 3：注入 v2 新增 env（M5 新增 `MEMORY_MCP_SESSION_SECRET`）**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && grep -q MEMORY_MCP_SESSION_SECRET .env && echo OK || echo MISSING'
```

如果输出 `MISSING`：

```bash
# Sir 在远端手动追加（不要写明文 secret 入 plan）：
# ssh <DEPLOY_HOST>
# cd ~/memory-mcp
# python3 -c "import secrets; print(f'MEMORY_MCP_SESSION_SECRET={secrets.token_urlsafe(48)}')" >> .env
# chmod 600 .env
```

VERIFY before proceed：再次 grep 输出 `OK`。

- [ ] **Step 4：构建新镜像（multi-stage 含 web build）**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose build memory-mcp 2>&1 | tail -50'
```

VERIFY before proceed：尾部 50 行无 `ERROR` / `failed`；最后含 `naming to docker.io/library/memory-mcp` 或同义成功标记。

- [ ] **Step 5：跑 migration（**最关键**，含 `--verify`）**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  TS=$(cat backups/.current_ts | cut -d= -f2) && \
  docker compose run --rm memory-mcp \
    python -m memory_mcp.scripts.migrate_v1_to_v2 \
      --src /app/data \
      --dst /app/data \
      --backup /app/backups/v1-data-$TS.tgz \
      --verify 2>&1 | tee /tmp/migration.log'
```

VERIFY before proceed：观察 `/tmp/migration.log` 末尾必须出现以下全部断言（spec §9.3）：
- `[verify] count(memories) == v1_count: OK`
- `[verify] entity FK consistency: OK`
- `[verify] LanceDB vectors aligned with memories: OK`
- `[verify] FTS5 rows == memories rows: OK`
- `[verify] relations FK resolved: OK`

**任何一条未通过 → 立即跳 Task 13（Rollback），不要 try-and-fix**。

- [ ] **Step 6：归档 migration 日志**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  TS=$(cat backups/.current_ts | cut -d= -f2) && \
  cp /tmp/migration.log "backups/migration-$TS.log" && \
  ls -lh backups/'
```

VERIFY before proceed：`backups/migration-<TS>.log` 存在。

### Task 9：启动新版 + health check

**Files：** 无（远程执行）

- [ ] **Step 1：拉起容器栈**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose up -d'
```

VERIFY before proceed：输出含 `Started` 对应 `memory-mcp` / `cloudflared` 容器。

- [ ] **Step 2：等待容器健康**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  for i in 1 2 3 4 5 6; do \
    sleep 5 && docker compose ps && \
    docker compose ps --format json | grep -q "\"Health\":\"healthy\"" && break; \
  done'
```

VERIFY before proceed：`docker compose ps` 显示 `memory-mcp` 为 `healthy`，`cloudflared` 为 `running`。

- [ ] **Step 3：外网 /health**

```bash
curl -fs https://<MEMORY_MCP_HOST>/health | jq
```

VERIFY before proceed：返回 JSON 含 `"status":"ok"`、`"vector_backend":"lancedb"`、`"sqlite_path":"/app/data/memory.sqlite3"`、`"schema_version":"0001_initial_v2"`（M1 `/health` 契约，见 spec D13）。

- [ ] **Step 4：检查 alembic 已升级到 head**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose exec memory-mcp mem db current 2>&1'
```

VERIFY before proceed：输出含 `0001_initial_v2` 或更新版本，且标 `(head)`。

- [ ] **Step 5：worker / scheduler 已起**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose logs --tail=100 memory-mcp 2>&1 | grep -iE "worker|scheduler|apscheduler"'
```

VERIFY before proceed：日志含 `worker loop started` / `APScheduler started` 一类标记；无 ERROR。

### Task 10：冒烟测试（本地 CLI + Web UI 双轨）

**Files：** 无（本地执行）

- [ ] **Step 1：本地 mem CLI 探活**

```bash
mem status
mem recall --all --limit 5
```

VERIFY before proceed：`status` 返回 `connected`；`recall --all` 返回旧数据（数量与 v1 一致），`origin_client` 为 null（v1 数据无该字段）。

> CLI 命令清单（spec D12）：`mem recall --all` 是历史命令，本 plan 全程沿用，不改 `mem recall_all`；by-id 通过 `mem memory get <id>` 子命令（M1 Task 20.5 注册的 `db_app`-style typer 子命令，与 `mem db ...` 同模式）。

- [ ] **Step 2：hybrid recall 探活**

```bash
mem recall "Sir 的偏好" --limit 3 --search-mode hybrid
```

VERIFY before proceed：返回 `results[].relevance_breakdown` 含 `rrf_score` / `vector_rank` / `fts_rank`；至少命中一条结果。

- [ ] **Step 3：thread sync 协议探活（dry-run，不写）**

```bash
mem thread sync --provider claude-code --dry-run
```

VERIFY before proceed：返回 `would push N batches` 一类输出，无 HTTP 4xx/5xx。

- [ ] **Step 4：Memory CRUD by id 探活**

```bash
# `mem recall --all` 默认 plain 文本输出，--format json 走 JSON envelope；items 是 D13 分页 DTO 标准字段名。
mem recall --all --limit 1 --format json | jq -r '.data.items[0].memory_id' | xargs -I {} mem memory get {}
```

VERIFY before proceed：返回 MemoryNode JSON 含 v2 新字段（`review_status` / `access_count` / `title`），其中 v1 数据 `review_status` 应为 `legacy`（spec §9.1）。

> 注意：`mem memory get` 由 M3 / M5 任一在 `cli/src/memory_mcp_cli/main.py` 增加 typer 子命令 `memory_app.command("get")`；调用 REST `GET /api/v1/memories/{id}`。如本地 CLI 尚未更新，临时退化用 `curl -fs -H "Authorization: Bearer <token>" https://<host>/api/v1/memories/<id> | jq` 直接打 REST 探活。

- [ ] **Step 5：Web UI 登录 + 列表 + 详情**

浏览器手动操作（在 `https://<MEMORY_MCP_HOST>/login`）：

```
1. 访问 /login → 输入 <MEMORY_MCP_AUTH_TOKEN>
2. 跳转 /memories → 看到旧数据列表（带 review_status=legacy 标记）
3. 点任一 memory → 进 /memories/:id → 看到详情 + EvolutionTimeline
4. 访问 /graph → 看到节点（react-flow + dagre）
5. 访问 /jobs → 看到 wm_refresh / reinforce_decay 等 cron 已 scheduled
6. 访问 /settings → 看到 sync 状态卡片
```

VERIFY before proceed：上述 6 步全部肉眼通过；浏览器 DevTools Network 面板无 4xx/5xx；Console 无 React 错误。

### Task 11：进入灰度（24h 观察）

**Files：** 无（被动观察）

- [ ] **Step 1：通知相关用户灰度开始**

服务已切换到 v2，请正常使用；如发现异常立即知会 Sir。

- [ ] **Step 2：第 1 小时检查（hook 推送 + worker 跑）**

本地正常用 Claude Code，触发若干 stop hook 自动推送：

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose logs --tail=200 memory-mcp 2>&1 | grep -iE "error|warning|failed|exception" | tail -30'
```

VERIFY before proceed：无 ERROR；warning 仅限可接受范围（如 LLM rate limit 偶发）。

```bash
mem recall --all --limit 5
```

VERIFY before proceed：count 比 cutover 时增加（hook 在写）。

```bash
# 查 jobs 表，确认无堆积失败
curl -fs -H "Authorization: Bearer <MEMORY_MCP_AUTH_TOKEN>" \
  "https://<MEMORY_MCP_HOST>/api/v1/jobs?status=failed&page=1" | jq '.data.total'
```

VERIFY before proceed：`failed` 数为 0，或 `attempts < max_attempts` 仍可重试。

- [ ] **Step 3：第 6 小时检查（thread sync + worker cron）**

```bash
mem thread sync --provider claude-code
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose logs --tail=50 memory-mcp 2>&1 | grep -iE "wm_refresh|reinforce_decay"'
```

VERIFY before proceed：thread sync 退出码 0；日志含至少一次 `wm_refresh` 完成（30min 一次的 cron）。

```bash
curl -fs -H "Authorization: Bearer <MEMORY_MCP_AUTH_TOKEN>" \
  "https://<MEMORY_MCP_HOST>/api/v1/threads?page=1&size=5" | jq '.data.total'
```

VERIFY before proceed：threads 数 > 0（hook 推送的实时增量已落库）。

- [ ] **Step 4：第 24 小时检查（reinforce_decay cron + 总体回归）**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose logs --since 25h memory-mcp 2>&1 | grep -iE "reinforce_decay"'
```

VERIFY before proceed：日志含至少一次 `reinforce_decay` 完成（每日 03:00 cron）。

```bash
# D13: 分页 DTO 字段名是 `items`，不是 `results`。
curl -fs -H "Authorization: Bearer <MEMORY_MCP_AUTH_TOKEN>" \
  "https://<MEMORY_MCP_HOST>/api/v1/jobs?status=failed&page=1" | jq '.data.items'
mem recall --all --limit 5
```

VERIFY before proceed：无 `attempts>=3 AND status=failed` 的任务；recall 数据持续增长；latency p95 与 v1 基线持平或更好（spec §13 缓解项观察）。

**任意检查发现以下情况之一 → 跳 Task 13（Rollback）：**
- 数据丢失或不一致（count 倒退、recall 拉不到旧数据）
- latency 显著突增（p95 > 2 × v1 基线）
- hook 推送链路断（threads 数 24h 内零增长但本地确实在用）
- worker 卡死（jobs 大量堆积在 `running` 状态超过 5min）

---

## Chunk 3：全量切换与收尾

### Task 12：全量切换标记与 AGENTS.md 更新

**Files：**
- Modify：`AGENTS.md`

> 灰度 24h 通过后无需额外操作（v2 已是稳态）。本 task 是文档收尾。

- [ ] **Step 1：更新 AGENTS.md 变更日志**

在 `AGENTS.md` 变更日志最顶部（紧接 `## 变更日志` 标题下）追加：

```markdown
### YYYY-MM-DD v2 Agent Kernel 上线（cutover 当日填入日期）
- 数据 schema 从 v1（LanceDB-only + JSON graph）一次性迁移到 v2（SQLite 主 + LanceDB 副）
- 启用 Hybrid Search（vector + FTS5/jieba + graph + reinforce + 时间衰减，RRF k=60）
- 启用 Threads 完整归档与本地 CLI sync 推送，stop hook 升级为双步（incremental + extract）
- 启用 Web UI 治理台（React 19 + TS 6 + Vite 8 + Tailwind v4 + shadcn，cookie session）
- 启用 Background Worker（同进程 asyncio + APScheduler + SQLite 队列）
- Memory CRUD by id + Memory Merge 上线，污染治理可操作
- 新增环境变量：MEMORY_MCP_SESSION_SECRET
- 备份：backups/v1-data-<MIGRATION_TS>.tgz + .sha256
- Release note：docs/releases/v2.0.0.md
```

- [ ] **Step 2：commit cutover 文档**

```bash
cd /Users/kassol/Workspace/memory-mcp
git add AGENTS.md
git commit -m "docs: log v2 production cutover"
git log --oneline -3
```

VERIFY before proceed：commit 落地；`git status` 干净。

- [ ] **Step 3（Sir 决定时机）：push main 与 tag**

```bash
# Sir 执行
git push origin main
git push origin v2.0.0
```

不要自动 push；助手仅在 Sir 明确说"push 上线收尾"后执行。

### Task 13：Rollback Runbook（独立 task，任何阶段失败立即触发）

**Files：** 无（远程执行）

> **触发条件**：Task 8 migration verify 失败 / Task 9 启动失败 / Task 10 冒烟失败 / Task 11 灰度发现严重回归。
>
> **决策原则**：rollback 优先于 try-and-fix。回到 v1 后再排查根因。

- [ ] **Step 1：停掉 v2 容器栈**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose down'
```

VERIFY before proceed：`docker compose ps` 显示无容器。

- [ ] **Step 2：删除 v2 数据目录**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  ls -la data/ && \
  echo "---确认上面是 v2 数据后回车删除---" && \
  rm -rf data/'
```

VERIFY before proceed：`data/` 已删；目录列出确认是 v2 结构（含 `memory.db` 等 SQLite 文件）。

- [ ] **Step 3：从备份恢复 v1 数据**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  TS=$(cat backups/.current_ts | cut -d= -f2) && \
  sha256sum -c "backups/v1-data-$TS.tgz.sha256" && \
  tar -xzf "backups/v1-data-$TS.tgz" && \
  ls -la data/'
```

VERIFY before proceed：sha256 校验 `OK`；`data/` 恢复出 `vectors/` / `graph/` 等 v1 结构；`.env` 也已恢复（包含 v1 时的全部 env，不含 `MEMORY_MCP_SESSION_SECRET` 也无妨）。

- [ ] **Step 4：checkout v1 tag**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && \
  git checkout <V1_TAG> && \
  git log --oneline -3'
```

VERIFY before proceed：HEAD 指向 `<V1_TAG>`。

- [ ] **Step 5：重建并启动 v1 容器**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && docker compose up -d --build'
```

VERIFY before proceed：`docker compose ps` 显示 v1 容器 `healthy`。

- [ ] **Step 6：v1 健康验证**

```bash
curl -fs https://<MEMORY_MCP_HOST>/health | jq
mem recall --all --limit 5
```

VERIFY before proceed：`/health` 返回 v1 期望结构（无 `sqlite_path` / `schema_version` 字段，只有 `status` + `vector_backend`）；`recall --all` 返回旧数据（与 cutover 前 count 一致）。

- [ ] **Step 7：通知 Sir + 排查方向**

回报内容模板（助手生成）：

```
Rollback 已完成。当前线上回到 <V1_TAG>。
原因：<具体哪一步 verify 失败 / 哪个回归>
关键日志：backups/migration-<TS>.log / docker compose logs
下一步排查方向：
  1. <根据具体失败类型给方向，如 migration FK 不一致 / FTS5 触发器异常 / vector backend 初始化失败>
  2. <在 dev 环境复现 / 修复 / 增加 fixture 覆盖>
  3. <修复后从 Task 4 重新打 tag 进入新一轮 cutover>
```

### Task 14：观察 24h 后清理与归档

**Files：**
- Read only：`backups/`

- [ ] **Step 1：旧 backup 保留策略**

```bash
ssh <DEPLOY_HOST> 'cd ~/memory-mcp && ls -lt backups/ | head -20'
```

VERIFY before proceed：当次 cutover 的 `v1-data-<MIGRATION_TS>.tgz` + `.sha256` + `migration-<TS>.log` 三件套都在。

策略：v1 backup 保留 30 天后清理（Sir 手动或加 cron），spec §13 风险表里的"migration 数据丢失"缓解项依赖此 backup。

- [ ] **Step 2：本地 backup 兜底归档**

```bash
ls -lh ~/Workspace/memory-mcp-backups/
```

VERIFY before proceed：本地 backup 仍在；Sir 可自行决定是否移到外接盘 / 云存储。

- [ ] **Step 3：migration 脚本不删**

migration 脚本 `src/memory_mcp/scripts/migrate_v1_to_v2.py` 留作 reference，下次跨大版本升级（如 v2 → v3）时仍可借鉴。

- [ ] **Step 4：v1 release branch 处理（如有）**

```bash
cd /Users/kassol/Workspace/memory-mcp
git branch -a | grep -i 'v1\|release'
```

如果存在 v1 release branch：

```bash
# Sir 决定是否关闭
# git branch -d <v1-branch>          # 已 merge 的本地分支
# git push origin --delete <v1-branch>  # 远端分支
```

不要自动删；助手仅在 Sir 明确指令时执行。

- [ ] **Step 5：通知 Sir 整个 M6 关闭**

回报内容模板：

```
M6 上线完成。
- v2.0.0 已生产稳定运行 24h+
- 文档：docs/releases/v2.0.0.md / AGENTS.md 变更日志
- 备份：backups/v1-data-<MIGRATION_TS>.tgz（远端 + 本地双备份，30 天后清理）
- 下一步：进入 Phase 2+ 路线（spec §12）
```

---

## 自检清单（plan 完成前过一遍）

- [x] spec §9.2 migration 命令完整：Task 8 Step 5 含 `--src/--dst/--backup/--verify` 全参数
- [x] spec §9.4 生产上线 6 步对应覆盖：通知（Chunk 2 开头）/ 停服（Task 7）/ 备份（Task 6）/ 构建+迁移（Task 8）/ 启动（Task 9）/ 回归（Task 10）/ 灰度（Task 11）
- [x] spec §9.5 rollback 独立 task：Task 13，含 sha256 校验、checkout v1 tag、重建启动、健康验证、回报模板
- [x] spec §13 风险缓解：migration 数据丢失（Task 6 双备份 + Task 8 verify + Task 13 rollback）/ hook 推送失败（Task 11 第 6/24h 通过 thread count 与 jobs 状态观察 + 本地 `mem thread sync` 兜底；M3 stop_hook_helper 已内置本地 retry queue）/ Token 泄露（Task 3 Step 2 grep + 占位符全局贯彻）
- [x] 无真实主机名 / 域名 / token / IP：全 plan 使用 `<DEPLOY_HOST>` / `<DEPLOY_DIR>` / `<MEMORY_MCP_HOST>` / `<MEMORY_MCP_AUTH_TOKEN>` / `<MEMORY_MCP_SESSION_SECRET>` / `<CLOUDFLARE_TUNNEL_TOKEN>` / `<V1_TAG>` / `<MIGRATION_TS>`
- [x] 无 TODO / TBD / placeholder：所有 step 给完整命令
- [x] git push 与 tag push 不自动执行：Task 4 Step 4 与 Task 12 Step 3 明确"Sir 决定时机"

---

## 修复记录

> 2026-05-21 plan 修复（codex 评审）：
>
> - **Task 9 Step 3（/health 字段）**：`/health` 返回 `{status, vector_backend, sqlite_path, schema_version}` 四字段（spec D13），断言改为校验 `sqlite_path` 与 `schema_version`，把旧 `db_path` 字面值删掉。
> - **Task 9 Step 4（mem db current）**：仍保留——M1 Task 20.5 已新增 `mem db upgrade/downgrade/current/history` 子命令，命令存在；plan 没动。
> - **Task 10 Step 1/4 / Task 11**：把 `mem recall_all` 一律改为 `mem recall --all`（现有 CLI 唯一形态，spec D12）；`mem memory_get` 改为 `mem memory get`（typer 子命令）；JSON 解析路径 `.results[0].memory_id` → `.data.items[0].memory_id`（D13 分页 DTO `items`）；保留 `curl REST` 退化路径以防 CLI 尚未更新。
> - **Task 11 Step 4（jobs API jq）**：`.data.results` → `.data.items`，与 M4 jobs handler 实际响应一致。
> - **Task 13 Step 6（rollback /health 断言）**：v1 `/health` 没有 `sqlite_path`/`schema_version`，明确写出来。
> - **占位符表（Chunk 1 开头）**：新增 `<DEPLOY_DIR>` 占位说明，标注「plan 文本仍用 `~/memory-mcp` 字面值，非默认部署位置时通读替换」——31 处 `~/memory-mcp` 不做批量改写以减少 PR diff。
> - **自检清单**：补一条 stop-hook 本地 retry queue（M3 已实现）说明，避免 reviewer 误以为只有服务端 `mem thread sync` 兜底。
