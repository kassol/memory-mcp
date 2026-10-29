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
- MCP 只暴露 agent 主动存取所需的 4 个工具（`remember` / `recall` / `forget` / `trace`），不注册 resources；运维与图谱类能力只走 REST / CLI
- Tool 返回值统一为 JSON 字符串
- 记忆数据持久化：向量存储 + 图存储并行
- 变更必须更新本文件
- 涉及线上服务能力的任务，只有更新到线上并完成线上验证后才算终结；仅完成本地代码、测试或文档不算完成

## 变更日志
### 2026-10-29 MCP 接口收敛为 4 个工具
- 动机：agent 只靠 MCP + 用户级 AGENTS.md 引导主动存取记忆。原 `remember` 要求调用方自起 `entity_key`，不同会话起的 key 会漂移，同一主题无法合并演化；8 个工具里多数与主动存取无关；`memory:///current`、`memory:///entities` 一次返回全部记忆，导入后 9000+ 条会撑爆客户端上下文。当时没有 MCP 客户端在用，不保留旧 MCP 契约
- MCP 只剩 `remember(content, title?, tags?)`、`recall(query, limit?)`、`forget(memory_id, reason?)`、`trace(entity_key, format?)`，schema 均 `additionalProperties: false`（多传参数返回 `Input validation error`）；description 写明各自使用时机
- 移除 MCP 的 `recall_all` / `relate` / `unrelate` / `graph_query` 工具与全部 resources / resource templates：`Server` 不再传 resources handler，initialize 不再声明 resources 能力，`resources/list` 返回 method not found。tool 函数、REST 路由、CLI 子命令保留
- `remember_tool`：`entity_key` / `entity_type` 改为可选（必须成对出现）；缺省时用同一份 embedding 调 `assign_entity_key` 分配，并跳过语义合并路径（key 分配已对照过最相似的 current 记忆，与 Extraction 一致）。显式传 key 的调用方（导入脚本、Extraction）行为不变；REST `POST /api/v1/memories` 同样可不传 key
- `forget_tool` 新增 `memory_id`：归档该条 current 记忆（写法与按 `entity_key` 归档相同）；id 不存在或不是 current 时抛错，MCP 返回 `{"error": ...}`；按 `entity_key` 的 REST / CLI 用法不变。未新增 REST 路由（`DELETE /api/v1/memories/{...}` 已被按 `entity_key` 归档占用）
- `recall` 返回项新增 `memory_id`，供 `forget` 使用
- `tests/test_transport.py` 契约测试改为 4 个工具 + 无 resources，并走通 remember（服务端分配 key）→ recall → forget → recall 流程

### 2026-10-29 部署改为宿主机反代，去掉 cloudflared
- 生产迁到 cc-la（1Panel OpenResty，host 网络）：`docker-compose.yml` 删除 cloudflared 服务，`memory-mcp` 只映射 `127.0.0.1:18765:8765`，由宿主机反代终结 HTTPS；`.env.example` / README 删除 `CLOUDFLARE_TUNNEL_TOKEN`
- `docs/testing.md` 手工集成步骤同步为 4 个 MCP 工具

### 2026-10-30 向量索引只存 current 并定期压实
- `VectorStore` 向量索引只保留 current 记忆：`insert` 只写 current 节点的向量，`update` 把节点置为非 current 时删除其向量，不再重写未变化的向量（内容变化一律是新节点）。所有检索都过滤 current，旧版本留在索引里会挤占 ANN 候选，长演化链上甚至会让 current 那条落到候选之外
- `LanceVectorBackend` 每 200 次写入执行一次 `optimize(cleanup_older_than=1h)`：原先每次写入新建一个 fragment 和 version，导入约 5.8k 条后积累 9479 个 fragment、18960 个 version、4.3GB，单条导入从约 5 秒退化到约 22 秒

### 2026-10-29 LLM 调用关闭推理
- `engine/llm.py` `chat()` 与 `check_conflict` 的请求统一带 `reasoning: {enabled: false}`（`NO_REASONING`）：OpenRouter 对部分模型（如 deepseek-v4.1-flash）默认开启推理，实测单次合并 10–28 秒、推理 token 最多约 8000，且偶发 content 为空；关闭后 1.7–3.3 秒，输出长度相当

### 2026-10-28 MCP Python SDK 迁移到 2.x
- 依赖约束 `mcp>=2.0,<3`；`requirements.lock`（`pip freeze | LC_ALL=C sort`，以旧锁为约束重解）与 `uv.lock` 同步更新
- `server.py` 由 1.x 装饰器注册改为 2.x `Server(..., on_list_tools/on_call_tool/on_list_resources/on_list_resource_templates/on_read_resource)` 构造参数，handler 签名 `(ctx, params)`，返回完整 Result 类型
- 2.x lowlevel 不再做 tool 入参 jsonschema 校验，`call_tool` 自行校验并保持 1.x 报错形态（`is_error=True` + `Input validation error: ...`）
- 对外 MCP 契约不变：8 个 tool、参数 schema、JSON 字符串返回、resources、`/mcp` 端点与 Bearer 鉴权；`transport/` 无需改动（`StreamableHTTPSessionManager` 签名未变）
- `tests/test_transport.py` 改用 2.x 进程内 `mcp.Client` 走真实协议分发，新增契约测试（tool 列表、校验报错、resources）
- 修复非 editable 安装（Dockerfile `pip install --no-deps .`）启动即崩：`storage/migrate.py` 改为按包内路径定位 migrations，`alembic.ini` 仅承载日志配置、找不到时省略（原先向上找 pyproject.toml 失败抛 `RuntimeError`）

### 2026-10-28 Nowledge 导入：key 分配 / 合并演化 / 冲突检测显式失败
- 新增 `engine/llm.py` `chat()`（单轮 OpenRouter 调用，HTTP/传输错误直接抛出），供 key 分配、合并、提取复用
- 新增 `engine/key_assignment.py` `assign_entity_key`：取 5 条最相似的 current 记忆给 LLM，同主题复用其 entity_key（类型以库内为准），否则新建 `<entity_type>:<snake_case>` key；请求失败或输出不可用抛 `KeyAssignmentError`
- Extraction Engine 的提取 LLM 只输出 `[{"content": ...}]`，entity_key/entity_type 一律由 `assign_entity_key` 对照库内记忆分配
- `check_conflict` 在请求失败、非 200、响应畸形、答案非 YES/NO 时抛 `ConflictCheckError`，不再当作「无冲突」
- 复用 key 时合并演化（`engine/merge.py` `merge_memories`）：`remember` 的两条演化路径在演化前让 LLM 把旧 current 与新内容合并为一条（保留不冲突的事实、冲突处以新内容为准、去重、保留 `[YYYY-MM]` 日期标注），新版本存合并结果并按合并文本重算 embedding；同 key 路径由这次合并调用同时给出 conflict（替代 `check_conflict`），语义合并路径仍先由 `check_conflict` 决定是否演化；合并结果与旧 current 相同返回 `no_change`；tags 取旧版与新输入的并集；合并失败抛 `MergeError`，不写库、不回退为整体替换。MCP / REST `remember` 同样生效，对外参数与返回字段不变
- `remember_tool` / `evolve_memory` 新增仅进程内可用的 `created_at` 参数：新节点 `created_at`/`valid_from` 与被演化旧节点的 `valid_until` 用该时间，未传时为当前时间；不暴露给 MCP/REST
- 新增 `python -m memory_mcp.scripts.import_nowledge --input <nmem --json m list 输出> --state <state.json> [--limit N] [--dry-run]`：`m list` 列出的全部记忆按 `created_at`（必须带时区）升序逐条分配 key 后经 `remember_tool`（`skip_semantic_merge`）写入，透传原 `created_at`、`origin_client=nowledge`、`origin_session_id=<Nowledge id>`、labels 作 tags；state 文件记录已完成与失败 id，可断点续跑；每条处理前先查库（`origin_client=nowledge` 且 `origin_session_id` 命中即视为已导入），写库后、存 state 前中断也不会重复提交；`--dry-run` 只解析排序，不调 LLM、不写库、不建 state 文件
- 合并提示词改为「保留长期有效事实、丢弃被新版本淘汰的阶段性状态（如旧进度快照）、结果 ≤1500 字」：试跑中逐条合并进度日志会把单条记忆滚到 1.1 万字以上，单条导入耗时随之升到约 21 秒
- 导入脚本 `--input` 可重复，多个来源按 `created_at` 穿插导入；记录可自带 `origin_client`（v1 线上数据用 `memory-mcp-v1`），续跑去重按 `origin_client + origin_session_id`；跳过 `memory-mcp-full-archive-*`（旧库整包转储，每条混装约 20 条无关记忆），v1 数据改为逐条导入
- key 分配与合并失败的报错带上底层异常，便于区分网络错误与模型输出问题

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
