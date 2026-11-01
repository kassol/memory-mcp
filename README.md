# Memory MCP

[English](README.en.md)

基于 **MCP Streamable HTTP** 的个人记忆服务：用 **语义向量检索** + **知识图谱** 持久化你的长期上下文，并支持对同一实体的记忆“演化”与冲突打标追溯。

## 特性

- **MCP Streamable HTTP**：不使用已废弃的 SSE
- **Bearer Token 鉴权**：`/mcp` 需要 `Authorization: Bearer <token>`（`/health` 免鉴权）
- **记忆演化而非覆盖**：同一 `entity_key` 多版本链路可追溯（`trace`）
- **冲突判定与打标**：命中也会判定并输出 `labels`：`conflict / correction / reversal`
- **混合检索**：`recall` 同时走向量（OpenRouter Embedding）、FTS5 关键词（jieba 预分词）与图一跳，按加权 RRF 融合，型号、版本号等字面信息也能命中
- **图谱关系**：实体关系入/出边 + BFS 深度查询（REST / CLI：`relate` / `graph_query`）
- **可测试/可落盘**：默认 LanceDB；可用 `MEMORY_MCP_VECTOR_BACKEND=memory` 作为无依赖后端

## 接口

- **MCP Endpoint**：`/mcp`（Streamable HTTP）
- **健康检查**：`/health`

## 快速开始（本地）

1. 安装依赖：`pip install .`
2. 准备环境变量：`cp .env.example .env` 并填写至少：
   - `MEMORY_MCP_AUTH_TOKEN`
   - `MEMORY_MCP_OPENROUTER_API_KEY`
3. 启动：`python -m memory_mcp`
4. 验证：`curl http://127.0.0.1:8765/health`

## Docker 部署（推荐）

1. 配置：`cp .env.example .env` 并填写必要变量
2. 构建并启动：`docker compose up -d --build`

说明：
- `docker-compose.yml` 只把服务绑到宿主机回环地址 `127.0.0.1:18765`，不直接暴露公网。
- 生产环境由宿主机上的反向代理终结 HTTPS，上游指向 `http://127.0.0.1:18765`。

## 环境变量

`.env.example` 已包含可用模板：

- **必填**
  - `MEMORY_MCP_AUTH_TOKEN`：鉴权 token
  - `MEMORY_MCP_OPENROUTER_API_KEY`：OpenRouter API Key
- **常用**
  - `MEMORY_MCP_HOST`：默认 `0.0.0.0`
  - `MEMORY_MCP_PORT`：默认 `8765`
  - `MEMORY_MCP_DATA_DIR`：默认 `./data`
  - `MEMORY_MCP_DEBUG`：默认 `false`
- **Embedding**
  - `MEMORY_MCP_OPENROUTER_BASE_URL`：默认 `https://openrouter.ai/api/v1`
  - `MEMORY_MCP_EMBEDDING_MODEL`：默认 `openai/text-embedding-3-small`
  - `MEMORY_MCP_EMBEDDING_DIM`：默认 `1536`
- **冲突判定（可选）**
  - `MEMORY_MCP_LLM_MODEL`：默认 `anthropic/claude-3-haiku`
  - `MEMORY_MCP_SIMILARITY_THRESHOLD`：默认 `0.85`（运行时设置，见下文「设置」）
- **向量后端（可选）**
  - `MEMORY_MCP_VECTOR_BACKEND`：`lancedb`（默认）/ `memory` / `auto`
  - 说明：生产建议使用 `lancedb`；LanceDB 启动失败会中止服务，避免旧记忆被静默隐藏
  - `memory` 适合测试；`auto` 会在 LanceDB 初始化失败时切换到 `memory`

## MCP 客户端配置示例

将域名与 token 替换为你自己的部署：

```json
{
  "mcpServers": {
    "memory-mcp": {
      "url": "https://memory-mcp.your-domain.com/mcp",
      "transport": { "type": "http" },
      "headers": {
        "Authorization": "Bearer your-secure-token-here"
      }
    }
  }
}
```

## Tools（工具）

MCP 只暴露 4 个工具，不提供 resources（全量记忆一次性返回会撑爆客户端上下文）：

- `remember(content, title?, tags?)`：写入一条长期有效的事实；`entity_key` 由服务端对照库内相似记忆分配，同主题自动合并演化并冲突打标
- `recall(query, limit?)`：混合检索当前记忆，返回项含 `memory_id`、`entity_key`、`content`、`created_at`；`relevance` 为融合分数，只在同一次结果内可比
- `forget(memory_id, reason?)`：按 id 归档一条当前记忆（不再作为 current）
- `trace(entity_key, format?)`：追溯某实体的演化链（timeline/summary）

`recall_all`、`relate`、`unrelate`、`graph_query` 与按 `entity_key` 归档只通过 REST API / CLI 提供。

## 数据落盘结构

默认目录为 `./data/`：

```
data/
├── vectors/                # 向量（LanceDB 或 memories.json）
└── graph/                  # 图谱 JSON
    ├── entities.json
    ├── relations.json
    └── evolution_chains.json
```

## 开发与测试

- 安装开发依赖：`pip install .[dev]`
- 运行测试：`pytest`
- 静态检查：`ruff check .`

更多测试说明见：`docs/testing.md`

## 许可证

本项目采用 MIT License，详见 `LICENSE`。

## 备份

部署主机上用 cron 每日执行 `ops/backup-db.sh`，在 `data/backups/` 下保留最近 7 份快照：`memory.sqlite3`、`vectors/`，以及 Provider API key 的加密数据密钥 `provider-keys.key`。恢复时停服务，用某个备份目录里的这三样覆盖 `data/` 下的同名文件，再启动。缺少数据密钥时库里的 API key 无法解密，面板会显示原因，需要重新填写 key。

## 管理面板

服务在 `/ui/` 提供管理面板（React 单页应用，源码在 `web/`）：概览、待审的发现、档案与版本历史（含检索记录）、维护轮次、设置。

- 面板用管理口令登录，与 agent 使用的访问令牌分开。首次部署时还没有口令：用配置文件里的访问令牌（`MEMORY_MCP_AUTH_TOKEN`）登录一次，随即设置管理口令；设置后访问令牌不能再登录面板
- 登录状态保存在 HttpOnly、Secure、SameSite=Strict 的 cookie 里，7 天有效，使用时自动延长；「设置 → 安全」可以修改口令、退出所有设备。面板必须经 HTTPS 访问（Secure cookie）
- 设置类接口（含访问令牌管理）只接受面板会话；记忆与发现接口同时接受访问令牌和面板会话；MCP 只接受访问令牌
- 访问令牌：「设置 → 访问令牌」为每个客户端（agent 所在主机、CLI 等）创建具名令牌，令牌值只在创建时显示一次，库里只存哈希；可以逐个吊销，吊销后名称保留、不能复用。配置文件里的令牌（`MEMORY_MCP_AUTH_TOKEN`）是初始令牌：服务首次启动时把它的哈希写进库里，之后与其他令牌一样可以吊销；之后再改配置文件里的值不会生效，只有口令重置命令会按当前值重新写入。每个令牌显示最近使用时间（每分钟最多更新一次）。经令牌写入的记忆在 `origin_token` 记下令牌名称。宿主机的维护定时任务（`ops/run-maintenance.sh`）读 `.env` 里的初始令牌，吊销初始令牌前先给它换成具名令牌
- REST：`GET /api/v1/tokens`、`POST /api/v1/tokens`（`{name}`，响应含 `value`）、`DELETE /api/v1/tokens/{id}`（吊销）
- 忘记口令：在部署主机的 compose 目录执行 `docker compose exec memory-mcp python -m memory_mcp.reset_password`，删除口令并退出所有面板会话，并把初始令牌按配置文件里的当前值重新写入、恢复生效（即使它已被吊销；对 agent 也生效），然后用它重新走首次登录。不再需要它时，设置口令后在面板里再吊销一次

- 镜像构建时由 Dockerfile 的 Node 阶段编译面板，产物放进 Python 包的 `ui/` 目录；产物不入库，运行镜像里没有 Node
- 概览页一屏看完：待审发现按类型计数（可跳转）、当前记忆与 7 / 30 天新增演化、最近一轮维护、Provider 最近调用、最久未更新的记忆、令牌最近使用，以及 30 天的写入 / 召回 / 召回耗时中位数图。对应 `GET /api/v1/overview`（只接受面板会话）
- 维护页可以立即跑一轮并刷新历史：开始时间、状态、耗时、模型调用次数、发现数与错误。对应 `GET /api/v1/overview/rounds?limit=`；计划本身在宿主机 cron 上，面板只展示
- 档案页可按 key、类型、写入时间、生效时间排序，按 key 与类型过滤；对应 `GET /api/v1/memories?sort=&direction=&key=&entity_type=`（返回 `matched` 为过滤后总数）与 `GET /api/v1/memories/types`
- 本地开发：`cd web && pnpm install && pnpm dev`（Vite 开发服务把 `/api` 代理到 `127.0.0.1:8765`）；`pnpm build` 把产物写进 `src/memory_mcp/ui/`
- 前端检查：`pnpm typecheck`、`pnpm lint`、`pnpm test`

## 设置

行为参数（语义合并门槛、维护单轮模型调用上限）和高级参数（混合检索与维护检查的数值，如 `fts_weight`、`rrf_k`、`cross_key_min_cosine`）可在面板「设置」页修改，保存后下一次调用即生效。生效值的优先级为：面板值 > 配置文件或环境变量（`MEMORY_MCP_<KEY>`，如 `MEMORY_MCP_FTS_WEIGHT`）> 默认值；面板显示每项的来源，可一键恢复为配置文件值。配置文件里超出范围的值会让服务启动失败并给出原因。REST（只接受面板会话）：`GET /api/v1/settings`、`PUT /api/v1/settings/{key}`（`{value}`）、`DELETE /api/v1/settings/{key}`（恢复）。

## Provider

模型服务入口。协议支持 OpenAI 兼容、Anthropic 与 Gemini（Anthropic 不提供 embedding）；每个 Provider 有自己的地址与 API key。

- 配置文件里的 OpenRouter 设置是一个来源为「配置文件」的 Provider。可以在面板里覆盖它的地址或 key，也可以一键恢复为配置文件值；它不能删除，协议固定为 OpenAI 兼容（向量用途依赖它）
- 面板新增的 Provider 可以编辑、替换 key、删除。API key 用 AES-GCM 加密存在 SQLite 里，数据密钥在 `data/provider-keys.key`（仅所有者可读，首次启动创建）；接口只返回末四位，换 key 时直接填新的，旧 key 不会回到浏览器
- 「测试连接」列出该 Provider 的模型，不消耗 token；列表页显示每个 Provider 最近一次调用的结果与时间，失败时显示原因
- REST（只接受面板会话）：`GET /api/v1/providers`、`POST /api/v1/providers`（`{name, protocol, base_url, api_key}`）、`PUT /api/v1/providers/{id}`（地址或 key 传 `null` 表示恢复配置文件值，仅配置文件 Provider 可这样做）、`DELETE /api/v1/providers/{id}`、`POST /api/v1/providers/test`（`{protocol, base_url, api_key?}` 或 `{id}`）、`GET /api/v1/providers/{id}/models`

## 启动设置

端口、数据目录、向量后端与调试日志只在启动时读取，改动要先校验再应用（面板「设置 → 启动设置」）：

- 改动先存成草稿，`校验` 逐条列出问题与原因：取值范围、数据目录存在且可写（换目录时里面要有现成的 `memory.sqlite3`）、向量后端能加载、已存向量维度与设置一致、容器外端口可绑定
- `应用并重启` 会再校验一次，然后停止接受请求、等一轮维护（最多 30 秒），进程以退出码 88 退出，由容器重启策略拉起（`docker-compose.yml` 里的 `restart: unless-stopped`）。手工运行且没有进程守护时，需要自己再启动一次
- 新设置起不来时（例如端口被占、数据目录不可用），下一次启动会回退到上一份可用的启动设置，并在面板显示回退原因
- 容器里端口与数据目录只读（由编排决定）；向量模型与维度只在配置文件里改：已存的向量是用它们算出来的
- 文件都在数据目录下：`startup-settings.json`（生效）、`startup-settings.pending.json`（草稿）、`startup-apply.json`（上次应用的结果）
- REST（只接受面板会话）：`GET /api/v1/startup-settings`、`PUT`（保存草稿）、`DELETE`（丢弃草稿）、`POST /api/v1/startup-settings/check`、`POST /api/v1/startup-settings/apply`

## 检索记录与统计

- 每次 recall 记一条检索记录：时间、访问令牌、查询文本、耗时、结果条数，以及前三条结果的 id；在面板「档案 → 检索记录」查看，可直接打开返回的记忆。保留 30 天，可一键清空
- 记录由设置 `recall_log_enabled` 控制（默认开，也可用 `MEMORY_MCP_RECALL_LOG_ENABLED`），关闭后不再记录
- 日统计与检索记录独立：按天与访问令牌统计写入数、召回数与召回耗时中位数，保留 90 天，关闭记录也照常统计
- REST（只接受面板会话）：`GET /api/v1/recall-log?limit=&offset=`、`GET /api/v1/recall-log/daily?days=`、`DELETE /api/v1/recall-log`（清空记录，统计保留）

## 模型用途

三类模型调用各自选择 Provider、模型与超时（面板「设置 → 模型用途」，保存后下一次调用即生效）：

- 写入：`remember` 时的 key 分配、合并与冲突判定，默认用配置文件 Provider 与 `MEMORY_MCP_LLM_MODEL`
- 维护：后台检查（内部矛盾、跨 key 重复）的判定，默认同上
- 向量：生成 embedding，只读。已存的向量是用它算出来的，改模型就无法与存量比较，所以只能在配置文件里改并重建全部向量；面板只显示 Provider、模型与维度

没有单独设置时用默认值（配置文件 Provider、`MEMORY_MCP_LLM_MODEL`、30 秒）；「恢复默认」删掉该用途的设置。删除 Provider 时若它正被某个用途使用，会被拒绝并指出用途。REST（只接受面板会话）：`GET /api/v1/model-roles`、`PUT /api/v1/model-roles/{role}`（`{provider_id, model, timeout}`）、`DELETE /api/v1/model-roles/{role}`、`POST /api/v1/model-roles/{role}/test`。

## 后台维护

维护检查找出需要人处理的记忆，结果称为「发现」（术语见 `GLOSSARY.md`）：跨 key 重复、内部矛盾、同 key 多条当前版本。检查只产生发现，不自动归档或合并。

- 服务不会自己启动维护。部署主机上用 cron 每日执行 `ops/run-maintenance.sh`（建议排在备份之后），它调用 `POST /api/v1/maintenance/run` 在后台跑一轮；已有一轮在跑时返回 409
- 每轮 LLM 调用数上限由设置 `maintenance_max_llm_calls` 控制（默认 100，面板或 `MEMORY_MCP_MAINTENANCE_MAX_LLM_CALLS`），没判完的留到下一轮
- 查看发现：`GET /api/v1/findings?status=open&kind=`；每轮的统计与错误记在 `jobs` 表（`job_type = 'maintenance'`）

示例 cron（`/etc/cron.d/memory-mcp-maintenance`，北京时间 04:17）：

```
17 20 * * * root /opt/memory-mcp/ops/run-maintenance.sh >> /var/log/memory-mcp-maintenance.log 2>&1
```
