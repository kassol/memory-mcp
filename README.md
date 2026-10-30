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
  - `MEMORY_MCP_SIMILARITY_THRESHOLD`：默认 `0.85`
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

部署主机上用 cron 每日执行 `ops/backup-db.sh`，在 `data/backups/` 下保留最近 7 份 SQLite 与向量库快照。恢复时停服务，用某个备份目录里的 `memory.sqlite3` 和 `vectors/` 覆盖 `data/` 下的同名文件，再启动。

## 后台维护

维护检查找出需要人处理的记忆，结果称为「发现」（术语见 `GLOSSARY.md`）：跨 key 重复、内部矛盾、同 key 多条当前版本。检查只产生发现，不自动归档或合并。

- 服务不会自己启动维护。部署主机上用 cron 每日执行 `ops/run-maintenance.sh`（建议排在备份之后），它调用 `POST /api/v1/maintenance/run` 在后台跑一轮；已有一轮在跑时返回 409
- 每轮 LLM 调用数上限由 `MEMORY_MCP_MAINTENANCE_MAX_LLM_CALLS` 控制（默认 100），没判完的留到下一轮
- 查看发现：`GET /api/v1/findings?status=open&kind=`；每轮的统计与错误记在 `jobs` 表（`job_type = 'maintenance'`）

示例 cron（`/etc/cron.d/memory-mcp-maintenance`，北京时间 04:17）：

```
17 20 * * * root /opt/memory-mcp/ops/run-maintenance.sh >> /var/log/memory-mcp-maintenance.log 2>&1
```
