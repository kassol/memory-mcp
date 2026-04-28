# Memory MCP

[English](README.en.md)

基于 **MCP Streamable HTTP** 的个人记忆服务：用 **语义向量检索** + **知识图谱** 持久化你的长期上下文，并支持对同一实体的记忆“演化”与冲突打标追溯。

## 特性

- **MCP Streamable HTTP**：不使用已废弃的 SSE
- **Bearer Token 鉴权**：`/mcp` 需要 `Authorization: Bearer <token>`（`/health` 免鉴权）
- **记忆演化而非覆盖**：同一 `entity_key` 多版本链路可追溯（`trace`）
- **冲突判定与打标**：命中也会判定并输出 `labels`：`conflict / correction / reversal`
- **语义检索**：通过 OpenRouter Embedding API 获取向量，支持相似度检索（`recall`）
- **图谱关系**：实体关系入/出边 + BFS 深度查询（`relate` / `graph_query`）
- **资源读取**：提供 `memory:///...` 资源给 MCP Client（current/entities/entity）
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
- 当前 `docker-compose.yml` **默认不暴露 8765**（避免直接公网暴露）。
- 若你需要在宿主机直接访问（本地调试），请在 `memory-mcp` service 增加端口映射：
  ```yaml
  ports:
    - "8765:8765"
  ```
- 生产环境建议通过 **Cloudflare Tunnel / 反向代理** 暴露 HTTPS。

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
- **Cloudflare Tunnel（可选）**
  - `CLOUDFLARE_TUNNEL_TOKEN`

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

- `remember`：写入/演化记忆（同 `entity_key` 自动演化与冲突打标）
- `recall`：按语义检索当前记忆（可选附带演化信息）
- `recall_all`：拉取全部当前记忆（用于初始化上下文）
- `trace`：追溯某实体的演化链（timeline/summary）
- `forget`：归档某实体当前记忆（不再作为 current）
- `relate`：创建实体关系边
- `unrelate`：按 relation id 删除实体关系边
- `graph_query`：按深度查询实体关系（入边+出边 BFS）

## Resources（资源）

- `memory:///current`：当前全部记忆（JSON）
- `memory:///entities`：实体列表（JSON）
- `memory:///entity/{entity_key}`：实体演化历史（JSON）

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
