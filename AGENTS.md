# Memory MCP

## 项目概述
个人记忆服务，基于语义向量检索与知识图谱，通过 MCP Streamable HTTP 对外提供能力。

## 技术栈
- Python 3.11+
- MCP SDK
- LanceDB
- NetworkX
- Starlette / Uvicorn

## 目录索引
- `src/` - 服务端源代码
- `tests/` - 服务端测试
- `cli/` - CLI 客户端（独立包 memory-mcp-cli）
- `claude-code-plugin/` - Claude Code 插件（hooks/skills/commands）
- `docs/` - 项目文档
- `data/` - 运行时数据

## 常用命令
- 安装依赖：`pip install .`
- 开发服务：`python -m memory_mcp`
- 运行测试：`pytest`
- 代码检查：`ruff check .`

## 全局规范
- MCP Streamable HTTP 为主传输协议；REST API (`/api/v1/*`) 为 CLI/hooks 等非 MCP 客户端提供轻量接入，复用同一套 tool 函数
- Tool 返回值统一为 JSON 字符串
- 记忆数据持久化：向量存储 + 图存储并行
- 变更必须更新本文件
- 涉及线上服务能力的任务，只有更新到线上并完成线上验证后才算终结；仅完成本地代码、测试或文档不算完成

## 变更日志
### 2026-05-21 M1 存储底座（v2 schema）
- 引入 SQLite v2 主存储（aiosqlite + alembic 1.18 + WAL/FK/busy_timeout pragmas）
- 新建 `0001_initial_v2` migration：memories / memories_fts / entities / relations / threads / thread_messages / thread_messages_fts / jobs / working_memory_cache + 全部索引 + FTS5 触发器
- LanceDB 精简到 `(id, vector)`，元数据全部走 SQLite；`VectorStore.search` 改为「ANN 取候选 ID → SQLite WHERE id IN (...) 拼装 MemoryNode」
- `GraphStore` 改为运行时按需把 `entities`/`relations` 加载进 `nx.MultiDiGraph`，写时双写，废弃 `data/graph/*.json` 持久化与 `evolution_chains.json`
- `MemoryNode` 增加 v2 字段：title / title_tokens / content_tokens / review_status / origin_client / origin_session_id / source_thread_id / source_refs / access_count / last_accessed_at / reinforce_count
- 应用层 jieba 分词，写入 memories 时自动填充 `content_tokens` / `title_tokens`，支持 `MEMORY_MCP_JIEBA_USER_DICT` 自定义词典
- 新增 `python -m memory_mcp.scripts.migrate_v1_to_v2 --src ... --dst ... --backup ... --dry-run --verify` 一次性迁移脚本（review_status 全部标 `legacy`）
- FastAPI lifespan 启动时自动跑 `alembic upgrade head`（`MEMORY_MCP_AUTO_MIGRATE` 控制）；`/health` 新增 `schema_version` 字段，`status` 由 `healthy` 改为 `ok`
- CLI 新增 `mem db upgrade/downgrade/current/history` 子命令（M6 runbook 离线运维入口）
- 7 个原有 MCP tools 对外契约保持不变；新字段全部默认值；hybrid search / memory_crud / threads / worker 留给 M2-M4

### 2026-04-29 Relation 删除能力与交付规则
- 新增 `unrelate` MCP tool，用于按 `relation_id` 删除实体关系边
- 新增 REST API `DELETE /api/v1/relations/{relation_id}`，返回 `deleted/not_found`
- CLI 新增 `mem unrelate <relation_id>`
- 明确交付规则：线上服务更新并验证通过才视为任务完成

### 2025-12-20 Streamable HTTP 与 PRD 补齐
- 替换 SSE 集成为 Streamable HTTP，会话由 SDK 管理
- 补齐 recall_all、资源读取、演化规则、图深度查询与归档原因
- 修复配置/存储问题并补充测试与文档
- 修复 Dockerfile 构建顺序，避免缺少源码/README 导致安装失败
- 增加向量存储 InMemory 后备实现（`MEMORY_MCP_VECTOR_BACKEND=memory`），提升可测试性与环境兼容性
- 补齐各子包 `__init__.py` 并拆分认证中间件到 `src/memory_mcp/transport/auth.py`
- `remember` 在 entity_key 命中时也执行冲突判定，并输出 `labels`（`conflict/correction/reversal`）用于打标与追溯
- `docker-compose.yml` 移除 8765 端口暴露，cloudflared 仅通过环境变量注入 token

### 2025-12-21 修复 Streamable HTTP 启动崩溃
- 修复 `StreamableHttpApp.lifespan` 方法签名以兼容 Starlette `lifespan(app)` 调用，解决容器启动 `TypeError` 崩溃
- 增加回归测试 `tests/test_transport.py`，确保生命周期钩子可正常进入/退出

### 2025-12-21 文档与开源协议完善
- 扩充 `README.md`（中文）功能介绍与使用说明，并新增英文版 `README.en.md`
- 新增 `LICENSE`（MIT License），便于 GitHub 开源分发

### 2026-03-25 Extension: REST API + CLI + Working Memory + Extraction + Plugin
- 新增 REST API (`/api/v1/*`) 作为辅助传输协议，复用现有 tool 函数
- 新增 `mem` CLI 客户端（httpx + typer），位于 `cli/` 目录
- 新增 Working Memory 引擎 — 模板拼接 briefing，无需 LLM
- 新增 Extraction Engine — LLM 从对话记录中提取候选记忆
- `remember_tool` 新增 `skip_semantic_merge` 参数，防止自动提取时跨实体污染
- 新增 Claude Code 插件（hooks: session-start/stop, skills, commands）
- AuthMiddleware 错误格式统一为 `{"ok": false, "error": ...}`
- 协议约束更新：MCP 主 + REST 辅

### 2026-03-25 Review Fixes: CLI / Extraction / Test Runner
- 修复 CLI `relate` 请求字段名错误，避免向 REST API 发送 `from_key/to_key` 导致 400
- CLI `remember` 补充 `--tags` 支持，并透传到 REST API
- Extraction Engine 在 LLM 调用失败时显式抛错，不再伪装为 `200 + empty results`
- 移除 `cli/tests/__init__.py`，修复根目录 `pytest` 因双 `tests` 包冲突导致的收集失败

### 2026-04-28 Production Deploy Hardening
- Dockerfile 改为使用 `requirements.lock` 安装锁定依赖，再以 `--no-deps` 安装本地包，降低重建时依赖漂移风险
- `MEMORY_MCP_VECTOR_BACKEND=lancedb` 下 LanceDB 初始化失败会直接中止启动；`memory` 与 `auto` 保留测试/兼容场景
- `/health` 返回当前 `vector_backend`，便于部署后确认实际存储后端
- Extraction Engine 返回单条候选写入失败的 `errors/failed`，便于排查部分写入失败

### 2026-05-21 v2 Agent Kernel Phase 1 设计与实施计划
- 新增 spec `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md`（13 个核心决策 D1-D13），覆盖 SQLite 主+Lance 副存储收敛、v2 schema 9 字段扩展（α/β/γ/δ/ε 五组）、Threads 完整归档、Hybrid Search、Web UI 治理台、Background Worker、生产破坏性迁移
- 新增 6 个 milestone plan（M1-M6，共 123 task / 579 step），每个 milestone 独立可 merge；待 M1 起实施
- 关键架构方向（实施中陆续生效）：存储收敛 SQLite 主+Lance 副、MemoryNode v2 字段扩展、Threads per-provider adapter、RRF hybrid search、cookie session Web UI、asyncio 同进程 worker、本地 CLI 推送式 sync
- 命名规范确立：分页响应字段 `items`（非 `results`）；REST by-id 路径 `/api/v1/memories/{id}`；CLI 引入 `mem db/memory/thread` 子命令簇；`/health` 字段固定 `{status, vector_backend, sqlite_path, schema_version}`
- 经 codex 交叉评审 + fix subagent 修复跨 plan 契约：7 项 Blocking（SQLite 抽象、MemoryNode v2 类型序列化、Thread FK 顺序、Worker DB 路径、REST/SPA DTO、M6 runbook 依赖、migration --dst）+ 6 项 Recommended + 4 项 Nice-to-have 全部清理
- Web UI 自动化 e2e 采用 agent-browser（不引入 Playwright 工具链）
