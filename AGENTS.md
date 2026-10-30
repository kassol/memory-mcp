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
- `docs/` - 项目文档
- `src/memory_mcp/ui/` - Web 治理台静态文件（HTML / CSS / 原生 JS，随包发布，挂在 `/ui/`）
- `PRODUCT.md` / `DESIGN.md` / `.impeccable/` - 治理台的产品与视觉记录（`.impeccable/review/` 等工作文件不入库）
- `ops/` - 部署主机上运行的运维脚本（`backup-db.sh`：SQLite + 向量库每日备份，保留 7 份；`run-maintenance.sh`：触发一轮后台维护）
- `data/` - 运行时数据

## 常用命令
- 安装依赖：`pip install .`
- 开发服务：`python -m memory_mcp`
- 运行测试：`pytest`
- 代码检查：`ruff check .`

## 全局规范
- MCP Streamable HTTP 为主传输协议；REST API (`/api/v1/*`) 为 CLI 等非 MCP 客户端提供轻量接入，复用同一套 tool 函数
- MCP 只暴露 agent 主动存取所需的 4 个工具（`remember` / `recall` / `forget` / `trace`），不注册 resources；运维与图谱类能力只走 REST / CLI
- Tool 返回值统一为 JSON 字符串
- 记忆数据持久化：向量存储 + 图存储并行
- 变更必须更新本文件
- 涉及线上服务能力的任务，只有更新到线上并完成线上验证后才算终结；仅完成本地代码、测试或文档不算完成

## Agent skills

### Issue tracker

Issue 与 spec 放在 GitHub Issues（kassol/memory-mcp），用 `gh` CLI 读写。See `docs/agents/issue-tracker.md`.

### Triage labels

五个标准分诊角色沿用默认标签名（needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix）。See `docs/agents/triage-labels.md`.

### Domain docs

单上下文：根目录 `GLOSSARY.md` + `docs/adr/`，按需创建。See `docs/agents/domain.md`.

## 变更日志
### 2026-10-30 Web 治理台（#6）
- 动机：维护检查产生的发现需要人来裁定，记忆写错时需要直接改正或归档；此前只能在 CLI 里逐条查
- `/ui/` 静态页面（HTML + CSS + 原生 JS，无构建链），由 Starlette `StaticFiles` 从包内目录托管，非 editable 安装下同样可用。`AuthMiddleware` 只对 `/ui` 与 `/ui/` 前缀放行；页面不含数据，令牌存 `sessionStorage`，所有数据请求带 Bearer，无 cookie。记忆文本只经 `textContent` 渲染（令牌在页面里，HTML 注入会泄露它），`tests/test_governance.py` 断言 `app.js` 不含 `innerHTML`
- 功能：待审发现队列（并排展示两条记忆、改正 / 归档任一条、判为误报）；档案列表（翻页、按类型过滤、按 `valid_from` 升序找久未更新的记忆、检索）；记忆详情与版本历史（改动类型、时间、冲突合并标记、归档原因）。列表为 listbox，支持方向键与 Enter / Space；每次列表与详情加载带序号，过期响应直接丢弃
- REST 新增：`GET /api/v1/memories/{memory_id}`（含全部版本，新在前）；`POST /api/v1/memories/{memory_id}/correct`（`{content}`，人工内容原样替换，不经 LLM 合并，只重算 embedding，保留 title 与来源字段；内容未变不生成新版本；非 current 返回 409）；`POST /api/v1/memories/{memory_id}/archive`（`{reason}` 必填，经 `forget_tool`；不存在 404、非 current 409）；`POST /api/v1/findings/{id}/dismiss`（一条带 `status = 'open'` 条件的 UPDATE，不覆盖并发自动关闭的结果；非 open 409）。`GET /api/v1/memories` 新增 `offset`、`order`（`created_at` / `valid_from`），返回项补 `memory_id` 与 `valid_from`，不带新参数时行为不变
- 按 id 的路由与 `{entity_key:path}` 路由共存：前者的 `{memory_id}` 不匹配 `/`，且方法或后缀不同，测试覆盖了带 `/` 的 entity_key 仍能 trace / forget
- `forget_tool` 抛出 `MemoryNotFound` / `MemoryNotCurrent`（`ValueError` 子类，MCP 与既有 REST 行为不变）
- 视觉：「档案登记簿」方向，系统字体、等宽只用于标识与日期，随系统深浅色；产品与设计记录见 `PRODUCT.md`、`DESIGN.md`。本地浏览器验证覆盖桌面 1440 / 960、手机 390、深浅色、键盘操作与请求竞态

### 2026-10-30 后台维护（#5）
- 动机：`remember` 只保证同一 key 内一致。跨 key 重复、合并残留过时事实造成的内部矛盾、中断留下的同 key 多条 current，之前没有机制发现。原记忆系统因后台任务占满 CPU 被弃用，所以维护只在被调用时运行
- 术语见 `GLOSSARY.md`：发现（Finding，需要人处理）与检查记录（Check，已判定过，含相容，只用于去重）
- 新增 `engine/maintenance.py`：`POST /api/v1/maintenance/run` 在服务进程内后台跑一轮，返回 202 与 job id，已有一轮在跑时 409；没有进程内定时循环，由宿主机 cron 调 `ops/run-maintenance.sh`。每轮在 `jobs` 表写一行（`payload` 为各项统计，失败写 `error` 并打 warning 日志）。服务关闭时取消正在跑的一轮并记为 failed
- 每轮顺序：自动关闭涉及记忆已非 current 的 open 发现；同 key 多条当前版本（SQL，open 或 dismissed 的不再重报）；内部矛盾（LLM，只查 `conflict=1` 的 current，线上 314 / 3903）；跨 key 重复（LLM，每条记忆用已存向量取余弦最近 5 个、不同 key、余弦 ≥ `CROSS_KEY_MIN_COSINE=0.85`，每个无序对判一次）。旧规则 relevance ≥ 0.85 线上只匹配 6 对，余弦 0.85 约 121 对
- 预算：`MEMORY_MCP_MAINTENANCE_MAX_LLM_CALLS`（默认 100）。两类 LLM 检查各一半，一类用不完的给另一类；没判完的留到下一轮。不用游标，待办即「没有检查记录的」，记忆演化后新 id 自然重新检查。邻居扫描记录只在该记忆所有候选对都有检查记录后才写
- LLM 输出不合法、请求失败或问题判定缺少 `detail` 时，记入本轮错误、不写检查记录，本轮跳过该项、下一轮重试；一条判不出的记忆不会挡住后面的检查。不当作相容
- 新增 migration `0004_maintenance_findings`：`memory_findings`（open / resolved / dismissed）与 `memory_checks`（主键 `check_type + subject`，pair 的 subject 为排序后的两个 id）。不复用 `memories.conflict`（它表示「本版本由冲突合并产生」）
- `VectorStore.cosine_neighbours`：用已存向量查余弦近邻，LanceDB 调用放在 `asyncio.to_thread`，不重算 embedding
- REST：`GET /api/v1/findings?status=&kind=`（只含发现，不含检查记录）。标为误报的接口归 Web 治理台（#6）。MCP 不变
- 线上首轮（积压 314 条 conflict=1 与 3903 条邻居扫描）：5 轮共 436 次 LLM 调用。邻居扫描阶段容器 CPU 中位约 230%、持续约 6 分钟，前台 recall 中位数不变、p95 668→830 ms、最大 2.5 s；清完积压后的轮次 CPU 峰值约 13%。全文抽查：跨 key 重复精确率 93%（14/15）；内部矛盾首版提示词 20%，收紧（同一对象同一属性、逐字引两段原文、排除缺陷记录 / 不同范围 / 已标明取代的演化）后 80%（含需人判断的边界项）；跨 key 矛盾 0%（13 条全是周期任务不同次执行），按决定去掉，配对只判重复 / 相容
- 测试：`tests/test_maintenance.py`（含 REST 202/409、预算分配与续跑、判定失败不阻塞、自动关闭、recall 在维护运行中不被阻塞）、`tests/test_migrations.py`、`tests/test_vector_backend.py`

### 2026-10-30 recall 混合检索（#4）
- 动机：纯向量对型号、版本号、数字这类字面信息不敏感。线上只读模拟（3903 条 current）：30 条「中文问法 + 稀有型号 / 版本串」查询，纯向量前 3 命中 3 条
- 新增 `engine/hybrid_search.py` `search(query, limit, entity_type=None)`：向量、FTS5、图一跳三路各取前 50（`CANDIDATES_PER_SOURCE`），加权 RRF（`k=60`，FTS 权重 `FTS_WEIGHT=2`）融合。等权时上述查询前 3 命中 9 条，FTS ×2 时 14 条；7 条原本命中的查询不退化。参数为模块常量，不加环境变量
- FTS 查询：jieba 切词，每个词按 FTS5 字符串加引号（双引号转义），去掉不含字母数字的词，以 OR 连接；切词为空时跳过 FTS
- 图一跳：前两路融合后前 5 个 `entity_key` 作为种子，取一跳邻居的 current 记忆，排除种子本身，最多 50 条。线上 `relations` 为 0 行，这一路目前没有贡献
- 时间衰减 `DECAY_LAMBDA` 默认 0（关闭），只有评估集显示有收益时才打开
- `MemoryRepository.fts_search` 只返回 current（FTS 索引含全部历史版本），支持 `entity_type`；改为 `CROSS JOIN`，强制先走 FTS：普通 JOIN 下 planner 从 `idx_memories_current` 出发，对每条 current 执行一次 MATCH，3.9k 行时 1.7–7.6 秒，改后约 10 ms。新增 `get_current_by_entity_keys`
- `VectorStore.search` 新增 `overfetch`（默认 4，行为不变）；混合检索无类型过滤时用 1：向量索引只存 current，ANN 后不会再丢结果，取 200 条比 50 条多约 55 ms
- `recall` 改为调用混合检索，MCP 与 REST 同时生效。MCP 入参与返回字段不变；`relevance` 改为融合分数，只保证同一次结果内越大越相关，tool description 已写明。REST `GET /api/v1/memories/search?explain=1` 额外返回 `vector_rank` / `fts_rank` / `graph_rank` / `rrf_score`
- 本地耗时（不含 embedding 请求，3903 current + 5603 历史版本，LanceDB 1536 维）：纯向量中位数 34 ms，混合检索 52 ms，增量约 18 ms
- 测试：`tests/test_hybrid_search.py`、`tests/test_retrieval_quality.py`（固定语料，含纯向量对照）；`tests/test_transport.py` 断言 `recall` 返回字段集合不变且拒收 `explain`

### 2026-10-30 测试关闭 SQLite 连接（#3）
- 存储测试在 `anyio.run()` 返回后才关闭 aiosqlite 连接，worker 线程把结果投递到已关闭的事件循环，pytest 报 `Event loop is closed`。三个存储测试文件改为在同一事件循环内关闭各自打开的 store

### 2026-10-30 例行备份
- 新增 `ops/backup-db.sh`：在 compose 目录执行，经容器内 Python 用 SQLite backup API 拷出一致快照（服务运行中也可执行），`integrity_check` 通过后再复制向量库，写入 `data/backups/<UTC 时间戳>/`，只在本次备份校验通过后才删除最旧的，保留 7 份。由部署主机的 cron 每日执行；部署同步排除 `data/`，不会删掉备份
- 恢复：停服务，用某个备份目录里的 `memory.sqlite3` 和 `vectors/` 覆盖 `data/` 下同名文件，再启动

### 2026-10-30 删除 working_memory_cache 表
- 新增 migration `0002_drop_working_memory_cache`：Working Memory 简报已删除，该表没有任何读写方；`downgrade` 按 0001 的定义重建空表。`schema.sql` 与 `tests/test_migrations.py` 同步，`/health.schema_version` 变为 `0002_drop_working_memory_cache`

### 2026-10-30 清理失效功能
- 动机：服务只通过 MCP 的 4 个工具和用户级 AGENTS.md 引导使用，不再走 hook；v1 线上实例已退役、数据已迁完；Nowledge 已全量导入并停用。以下代码和文档已无使用方，留着只会误导读者
- 删除 `claude-code-plugin/`（session-start / stop hook、skills、commands）
- 删除 Working Memory 与对话提取：`engine/working_memory.py`、`engine/extraction.py`，REST `GET /api/v1/wm`、`POST /api/v1/memories/extract`，CLI `mem wm`、`mem extract` 及 client 对应方法，相关测试。`key_assignment` / `merge` / `llm` 仍被 `remember` 使用，保留。`working_memory_cache` 表保留在 schema 中（删表需要新 migration）
- 删除 v1 迁移：`scripts/migrate_v1_to_v2.py`、`tests/test_migrate_v1_to_v2.py`、`tests/fixtures/`，以及 `.gitignore`、ruff `extend-exclude` 里对 fixture 的例外；`storage/migrate.py` `run_migrations` / `_make_config` 的 `db_path` 参数随之无调用方，一并删除
- 删除 Nowledge 导入：`scripts/import_nowledge.py`、`tests/test_import_nowledge.py`；`scripts/` 包已空，删除。`remember_tool` 的仅进程内参数 `embedding` / `created_at` 与 `evolve_memory` 的 `created_at` 只有导入脚本和 Extraction 在用，一并删除，新节点时间一律取当前时间
- 删除 `docs/prd.md`（2024 年初版 PRD，架构与工具清单已过时）、`docs/behavioral-guidance.md`（基于 `mem` CLI 与 `mem wm` 的提示词，已被用户级 AGENTS.md 引导取代）
- 文档与代码中的生产主机别名和面板名改为中性说法（仓库公开）
- 删除 `docs/superpowers/`（2026-03 extension 与 2026-05 Agent Kernel 的 spec 和 M1–M6 plan）：M1 已落地，M6 已用其他方式完成，M3 不做；M2 混合检索、M4 后台维护、M5 Web 治理台中仍成立的部分已转为 GitHub issue #4、#5、#6
### 2026-10-30 Agent skills 配置
- 新增 `docs/agents/`（issue-tracker / triage-labels / domain）与本文件 `## Agent skills` 一节：issue 走 GitHub Issues，分诊标签沿用默认五个（已在 GitHub 补建 needs-triage / needs-info / ready-for-agent / ready-for-human），领域文档为单上下文布局
- 项目 backlog（含 C 档积压）以 GitHub Issues 为准

### 2026-10-29 MCP 接口收敛为 4 个工具
- 动机：agent 只靠 MCP + 用户级 AGENTS.md 引导主动存取记忆。原 `remember` 要求调用方自起 `entity_key`，不同会话起的 key 会漂移，同一主题无法合并演化；8 个工具里多数与主动存取无关；`memory:///current`、`memory:///entities` 一次返回全部记忆，导入后 9000+ 条会撑爆客户端上下文。当时没有 MCP 客户端在用，不保留旧 MCP 契约
- MCP 只剩 `remember(content, title?, tags?)`、`recall(query, limit?)`、`forget(memory_id, reason?)`、`trace(entity_key, format?)`，schema 均 `additionalProperties: false`（多传参数返回 `Input validation error`）；description 写明各自使用时机
- 移除 MCP 的 `recall_all` / `relate` / `unrelate` / `graph_query` 工具与全部 resources / resource templates：`Server` 不再传 resources handler，initialize 不再声明 resources 能力，`resources/list` 返回 method not found。tool 函数、REST 路由、CLI 子命令保留
- `remember_tool`：`entity_key` / `entity_type` 改为可选（必须成对出现）；缺省时用同一份 embedding 调 `assign_entity_key` 分配，并跳过语义合并路径（key 分配已对照过最相似的 current 记忆，与 Extraction 一致）。显式传 key 的调用方（导入脚本、Extraction）行为不变；REST `POST /api/v1/memories` 同样可不传 key
- `forget_tool` 新增 `memory_id`：归档该条 current 记忆（写法与按 `entity_key` 归档相同）；id 不存在或不是 current 时抛错，MCP 返回 `{"error": ...}`；按 `entity_key` 的 REST / CLI 用法不变。未新增 REST 路由（`DELETE /api/v1/memories/{...}` 已被按 `entity_key` 归档占用）
- `recall` 返回项新增 `memory_id`，供 `forget` 使用
- `tests/test_transport.py` 契约测试改为 4 个工具 + 无 resources，并走通 remember（服务端分配 key）→ recall → forget → recall 流程

### 2026-10-29 部署改为宿主机反代，去掉 cloudflared
- 生产迁到新主机，由宿主机上的反向代理（host 网络）终结 HTTPS：`docker-compose.yml` 删除 cloudflared 服务，`memory-mcp` 只映射 `127.0.0.1:18765:8765`；`.env.example` / README 删除 `CLOUDFLARE_TUNNEL_TOKEN`
- `docs/testing.md` 手工集成步骤同步为 4 个 MCP 工具

### 2026-10-30 向量表跨进程可见
- `LanceVectorBackend` 以 `read_consistency_interval=0` 连接：服务进程每次读都检查新版本。原先服务一直使用启动时打开的快照，导入脚本等其他进程写入的向量要重启服务才能检索到（Nowledge 增量导入后实测）

### 2026-10-30 演化写入顺序
- `evolve_memory` 新增 `fields`，`remember` 把 origin_client / origin_session_id / source_thread_id / source_refs / title 随新节点一次 insert 写入，不再演化后补一次 update。原先两次写入之间中断会留下缺来源的 current 记忆，导入去重也认不出它（全量导入中实际出现 1 条）
- 先 insert 新版本、再把旧版本置为非 current：中断时最坏是同一主题有两条 current，而不是一条都没有

### 2026-10-30 key 规范化与合并输出容错
- `assign_entity_key` 新建 key 时不再因格式拒收：转小写，subject 中非 `[a-z0-9_]` 字符替换为 `_`，以 key 前缀作为 entity_type；规范化后命中邻居 key 则沿用。仍拒收没有 `type:` 前缀或 subject 为空的输出。全量导入中 4 条失败来自主机名、`qwen3.6` 这类 subject 与前缀/类型不一致
- `merge_memories` 以 `json.loads(strict=False)` 解析，接受 content 字符串里的字面换行；解析失败时报错带 JSON 错误位置与上下文。全量导入中 20 条合并失败为偶发输出不规范，原样重试即通过

### 2026-10-30 向量索引只存 current 并定期压实
- `VectorStore` 向量索引只保留 current 记忆：`insert` 只写 current 节点的向量，`update` 把节点置为非 current 时删除其向量，不再重写未变化的向量（内容变化一律是新节点）。所有检索都过滤 current，旧版本留在索引里会挤占 ANN 候选，长演化链上甚至会让 current 那条落到候选之外
- `LanceVectorBackend` 每 200 次写入执行一次 `optimize(cleanup_older_than=1h)`：原先每次写入新建一个 fragment 和 version，导入约 5.8k 条后积累 9479 个 fragment、18960 个 version、4.3GB，单条导入从约 5 秒退化到约 22 秒

### 2026-10-30 删除线程表与线程溯源字段
- 新增 migration `0003_drop_threads`：删除 `threads` / `thread_messages` / `thread_messages_fts` 及其索引与触发器，删除 `memories.source_thread_id` / `source_refs` 两列、`idx_memories_source_thread_id` 与指向 `threads` 的外键。线上这两张表与两列均无数据，代码也不再读写
- SQLite 无法删除带外键的列，`memories` 按官方 12 步流程重建：在 alembic `autocommit_block` 里先关外键再显式 `BEGIN`（PRAGMA 在事务内不生效），`INSERT ... SELECT rowid, ...` 保留 rowid（`memories_fts` 是按 rowid 对应的 external-content 索引），重建索引与 FTS 触发器后执行 FTS `rebuild`，`foreign_key_check` 非空即回滚并报错，提交后重新开外键。downgrade 用同一流程恢复线程表与两列（取 NULL）
- `MemoryNode` 删除 `source_thread_id` / `source_refs` 与 `SourceRef`；`remember` 不再读取这两个参数，REST 请求体带上时静默忽略；MCP schema 不变
- `schema.sql` 同步为 0003 之后的结构；`tests/test_migrations.py` 覆盖升级、降级前后的行数、rowid 与 id 对应、FTS 命中、外键与完整性检查

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
