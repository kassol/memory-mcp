# Memory MCP - 个人记忆服务

## 产品需求文档 (PRD)

**版本**：1.0  
**日期**：2024-12-20  
**作者**：J.A.R.V.I.S. for Kassol

---

## 1. 概述

### 1.1 产品愿景

构建一个基于 **语义向量检索** 与 **知识图谱** 的个人记忆服务，通过 MCP（Model Context Protocol）标准协议对外提供能力，使 AI 助手具备真正的长期记忆：不仅记住事实，更能追溯认知的演变过程。

### 1.2 核心理念

> **记忆不是快照，是一条河流。**

- 记忆不删除、不覆盖，而是**演化**
- 每个当前状态都能追溯**由来**
- 支持语义检索与结构化查询

### 1.3 目标用户

- 个人开发者，希望为自己的 AI 助手添加持久记忆
- 需要跨会话保持上下文连续性的场景

---

## 2. 技术架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MCP Client (Claude/Cursor/IDE)                  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS (via Cloudflare Tunnel)
                                │ Authorization: Bearer <TOKEN>
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Cloudflare Tunnel                           │
│                    (memory-mcp.your-domain.com)                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP (internal)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Memory MCP Server                             │
│                         (Docker Container)                          │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Streamable HTTP Transport                   │ │
│  │                  POST/GET /mcp (JSON-RPC 2.0)                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                │                                    │
│  ┌─────────────┐  ┌────────────▼───────────┐  ┌─────────────────┐  │
│  │    Tools    │  │     Memory Engine      │  │    Resources    │  │
│  │  - remember │  │  - ConflictDetector    │  │  - memory://    │  │
│  │  - recall   │  │  - EvolutionManager    │  │                 │  │
│  │  - evolve   │  │  - QueryPlanner        │  │                 │  │
│  │  - trace    │  │                        │  │                 │  │
│  └─────────────┘  └────────────┬───────────┘  └─────────────────┘  │
│                                │                                    │
│  ┌─────────────────────────────┴───────────────────────────────┐   │
│  │                      Storage Layer                           │   │
│  │  ┌─────────────────────┐    ┌─────────────────────────────┐ │   │
│  │  │   Vector Store      │    │      Graph Store            │ │   │
│  │  │   (LanceDB)         │◄──►│      (NetworkX +            │ │   │
│  │  │   ./data/vectors/   │    │       JSON Persistence)     │ │   │
│  │  └─────────────────────┘    └─────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                │                                    │
│  ┌─────────────────────────────┴───────────────────────────────┐   │
│  │                    Embedding Service                         │   │
│  │              (OpenRouter API - Remote Call)                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| **语言** | Python 3.11+ | MCP SDK 成熟度最高 |
| **MCP 框架** | `mcp` 官方 SDK | 原生支持 Streamable HTTP |
| **HTTP 传输** | Streamable HTTP | MCP 2025-03-26 规范标准 |
| **向量数据库** | LanceDB | 嵌入式、文件存储、零配置 |
| **图存储** | NetworkX + JSON | 轻量级、文件持久化、无外部依赖 |
| **Embedding** | OpenRouter API | 统一接口、多模型支持 |
| **Embedding 模型** | `openai/text-embedding-3-small` | 性价比最优 |
| **部署** | Docker Compose | 标准化、可移植 |
| **隧道** | Cloudflare Tunnel | 免费、安全、无需公网 IP |
| **认证** | Bearer Token | 简单、部署时配置 |

### 2.3 数据存储结构

```
./data/
├── vectors/                    # LanceDB 向量数据
│   └── memories.lance/
├── graph/                      # 图数据（JSON）
│   ├── entities.json
│   ├── relations.json
│   └── evolution_chains.json
└── config/
    └── settings.json
```

---

## 3. 核心数据模型

### 3.1 记忆节点 (MemoryNode)

```python
class MutationType(str, Enum):
    INITIAL = "initial"           # 首次记录
    UPDATE = "update"             # 信息更新（同一事实的新值）
    REFINEMENT = "refinement"     # 细化补充（更多细节）
    CORRECTION = "correction"     # 纠正错误
    REVERSAL = "reversal"         # 观点反转
    EVOLUTION = "evolution"       # 自然演进

class MemoryNode(BaseModel):
    # 标识
    id: str                               # UUID
    entity_key: str                       # 唯一实体标识，如 "preference:programming_language"
    entity_type: str                      # person | preference | fact | event | goal | project
    
    # 内容
    content: str                          # 记忆内容（自然语言）
    embedding: List[float]                # 向量表示（1536维）
    
    # 演化链
    parent_id: Optional[str]              # 前一版本节点 ID（None = 初始记忆）
    mutation_type: MutationType           # 变更类型
    mutation_reason: Optional[str]        # 变更原因/触发事件描述
    
    # 时间
    created_at: datetime                  # 创建时间
    valid_from: datetime                  # 生效时间
    valid_until: Optional[datetime]       # 失效时间（None = 当前有效）
    
    # 状态
    is_current: bool                      # 是否为最新状态
    confidence: float                     # 置信度 0-1
    
    # 元数据
    tags: List[str]                       # 标签
    source: str                           # 来源：conversation | import | inference
```

### 3.2 实体 (Entity)

```python
class Entity(BaseModel):
    id: str
    name: str                             # 人类可读名称
    entity_key: str                       # 唯一标识
    entity_type: str
    current_memory_id: Optional[str]      # 当前最新记忆节点
    created_at: datetime
    updated_at: datetime
```

### 3.3 关系 (Relation)

```python
class Relation(BaseModel):
    id: str
    from_entity_key: str
    to_entity_key: str
    relation_type: str                    # KNOWS | PREFERS | WORKS_ON | RELATED_TO 等
    properties: Dict[str, Any]
    created_at: datetime
```

### 3.4 演化链可视化示例

```
[preference:tech_stack]

[2023-06] INITIAL
    │     "主要使用 Python 进行开发"
    │
    ▼
[2023-09] REFINEMENT
    │     "主要使用 Python，开始关注 Rust"
    │     reason: "提到在学习 Rust 内存管理"
    │
    ▼
[2024-03] EVOLUTION
    │     "Python 为主，Rust 用于性能敏感模块"
    │     reason: "完成了第一个 Rust 生产项目"
    │
    ▼
[2024-12] CURRENT ✓
          "技术栈：Python + Rust，正在探索 Zig"
          reason: "对话中表达了对 Zig 的兴趣"
```

---

## 4. MCP 接口设计

### 4.1 传输协议

**Streamable HTTP Transport**（MCP 2025-03-26 规范）

- **端点**：`POST /mcp` 与 `GET /mcp`
- **内容类型**：`application/json` 或 `text/event-stream`
- **认证**：`Authorization: Bearer <TOKEN>`
- **会话管理**：通过 `Mcp-Session-Id` header

### 4.2 认证流程

```
Client                                Server
  │                                     │
  │  POST /mcp                          │
  │  Authorization: Bearer <TOKEN>      │
  │  Body: InitializeRequest            │
  │─────────────────────────────────────>│
  │                                     │
  │  200 OK                             │
  │  Mcp-Session-Id: <SESSION_ID>       │
  │  Body: InitializeResult             │
  │<─────────────────────────────────────│
  │                                     │
  │  (后续请求携带 Session ID)           │
  │  POST /mcp                          │
  │  Authorization: Bearer <TOKEN>      │
  │  Mcp-Session-Id: <SESSION_ID>       │
  │─────────────────────────────────────>│
```

### 4.3 Tools 定义

#### 4.3.1 `remember` - 记忆写入

**描述**：存储新的记忆。系统自动检测冲突并创建演化链。

**输入 Schema**：
```json
{
  "type": "object",
  "properties": {
    "content": {
      "type": "string",
      "description": "要记住的内容"
    },
    "entity_type": {
      "type": "string",
      "enum": ["person", "preference", "fact", "event", "goal", "project"],
      "description": "实体类型"
    },
    "entity_key": {
      "type": "string",
      "description": "实体唯一标识，格式建议：type:name，如 preference:editor"
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "可选标签"
    }
  },
  "required": ["content", "entity_type", "entity_key"]
}
```

**输出示例**：
```json
{
  "status": "evolved",
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "entity_key": "preference:editor",
  "mutation_type": "evolution",
  "mutation_reason": "从 VSCode 转向 Cursor",
  "parent_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

#### 4.3.2 `recall` - 记忆检索

**描述**：语义检索相关记忆，仅返回当前有效的记忆。

**输入 Schema**：
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "搜索查询（自然语言）"
    },
    "entity_type": {
      "type": "string",
      "description": "限定实体类型（可选）"
    },
    "limit": {
      "type": "integer",
      "default": 10,
      "description": "返回数量上限"
    },
    "include_evolution": {
      "type": "boolean",
      "default": false,
      "description": "是否包含演化历史摘要"
    }
  },
  "required": ["query"]
}
```

**输出示例**：
```json
{
  "results": [
    {
      "entity_key": "preference:editor",
      "content": "主要使用 Cursor 作为代码编辑器",
      "relevance": 0.89,
      "entity_type": "preference",
      "evolution_count": 3,
      "last_mutation": "evolution"
    }
  ],
  "total": 1
}
```

#### 4.3.3 `recall_all` - 全量记忆获取

**描述**：获取所有当前有效的记忆，用于对话启动时的上下文加载。

**输入 Schema**：
```json
{
  "type": "object",
  "properties": {
    "entity_type": {
      "type": "string",
      "description": "限定实体类型（可选）"
    },
    "limit": {
      "type": "integer",
      "default": 100,
      "description": "返回数量上限"
    }
  }
}
```

#### 4.3.4 `trace` - 演化链追溯

**描述**：追溯一条记忆的完整演化历史。

**输入 Schema**：
```json
{
  "type": "object",
  "properties": {
    "entity_key": {
      "type": "string",
      "description": "实体标识"
    },
    "format": {
      "type": "string",
      "enum": ["timeline", "summary"],
      "default": "timeline",
      "description": "输出格式"
    }
  },
  "required": ["entity_key"]
}
```

**输出示例（timeline）**：
```json
{
  "entity_key": "preference:editor",
  "chain": [
    {
      "id": "...",
      "content": "使用 Sublime Text",
      "mutation_type": "initial",
      "created_at": "2022-01-15T10:00:00Z"
    },
    {
      "id": "...",
      "content": "迁移到 VSCode",
      "mutation_type": "evolution",
      "mutation_reason": "需要更好的扩展生态",
      "created_at": "2023-03-20T14:30:00Z"
    },
    {
      "id": "...",
      "content": "主要使用 Cursor 作为代码编辑器",
      "mutation_type": "evolution",
      "mutation_reason": "AI 辅助编程需求",
      "created_at": "2024-08-10T09:15:00Z",
      "is_current": true
    }
  ],
  "total_versions": 3
}
```

#### 4.3.5 `forget` - 记忆归档

**描述**：将指定记忆标记为归档状态（不删除，但不再参与常规检索）。

**输入 Schema**：
```json
{
  "type": "object",
  "properties": {
    "entity_key": {
      "type": "string",
      "description": "实体标识"
    },
    "reason": {
      "type": "string",
      "description": "归档原因"
    }
  },
  "required": ["entity_key"]
}
```

#### 4.3.6 `relate` - 建立关系

**描述**：在两个实体之间建立关系。

**输入 Schema**：
```json
{
  "type": "object",
  "properties": {
    "from_entity_key": {
      "type": "string"
    },
    "to_entity_key": {
      "type": "string"
    },
    "relation_type": {
      "type": "string",
      "description": "关系类型，如 KNOWS, WORKS_ON, PREFERS"
    },
    "properties": {
      "type": "object",
      "description": "关系属性"
    }
  },
  "required": ["from_entity_key", "to_entity_key", "relation_type"]
}
```

#### 4.3.7 `graph_query` - 图查询

**描述**：查询实体的关系网络。

**输入 Schema**：
```json
{
  "type": "object",
  "properties": {
    "entity_key": {
      "type": "string",
      "description": "起始实体"
    },
    "relation_types": {
      "type": "array",
      "items": { "type": "string" },
      "description": "限定关系类型"
    },
    "depth": {
      "type": "integer",
      "default": 1,
      "description": "遍历深度"
    }
  },
  "required": ["entity_key"]
}
```

---

## 5. 核心引擎逻辑

### 5.1 记忆写入流程

```
新信息输入
    │
    ▼
┌─────────────────┐
│  生成 Embedding │ ──────────────────────────────────┐
└────────┬────────┘                                   │
         │                                            │
         ▼                                            │
┌─────────────────┐                                   │
│  entity_key     │                                   │
│  精确匹配检索   │                                   │
└────────┬────────┘                                   │
         │                                            │
    ┌────▼────┐                                       │
    │ 命中？  │                                       │
    └────┬────┘                                       │
         │                                            │
    ┌────┴────┐                                       │
   Yes        No                                      │
    │         │                                       │
    ▼         ▼                                       │
┌────────┐  ┌──────────────────┐                      │
│  演化  │  │ 语义相似度检索   │ ◄────────────────────┘
│  处理  │  │ (threshold=0.85) │
└───┬────┘  └────────┬─────────┘
    │                │
    │           ┌────▼────┐
    │           │ 有相似？ │
    │           └────┬────┘
    │                │
    │           ┌────┴────┐
    │          Yes        No
    │           │         │
    │           ▼         ▼
    │       ┌────────┐  ┌────────┐
    │       │ LLM判断 │  │ 新建   │
    │       │ 是否冲突│  │ 记忆   │
    │       └───┬────┘  └────────┘
    │           │
    │      ┌────┴────┐
    │     Yes        No
    │      │         │
    │      ▼         ▼
    │  ┌────────┐  ┌────────┐
    └─►│  演化  │  │  新建  │
       │  处理  │  │  记忆  │
       └────────┘  └────────┘
```

### 5.2 演化处理逻辑

```python
async def evolve_memory(
    new_content: str,
    existing_node: MemoryNode,
    embedding: List[float]
) -> MemoryNode:
    
    # 1. 推断变更类型
    mutation_type = infer_mutation_type(
        old=existing_node.content,
        new=new_content
    )
    
    # 2. 生成变更原因
    mutation_reason = generate_mutation_reason(
        old=existing_node.content,
        new=new_content,
        mutation_type=mutation_type
    )
    
    # 3. 创建新节点
    new_node = MemoryNode(
        id=uuid4(),
        entity_key=existing_node.entity_key,
        entity_type=existing_node.entity_type,
        content=new_content,
        embedding=embedding,
        parent_id=existing_node.id,
        mutation_type=mutation_type,
        mutation_reason=mutation_reason,
        is_current=True
    )
    
    # 4. 更新旧节点
    existing_node.is_current = False
    existing_node.valid_until = datetime.utcnow()
    
    # 5. 持久化
    await vector_store.update(existing_node)
    await vector_store.insert(new_node)
    await graph_store.add_evolution_edge(
        from_id=existing_node.id,
        to_id=new_node.id
    )
    
    return new_node
```

### 5.3 变更类型推断规则

| 规则 | 条件 | 类型 |
|------|------|------|
| 反转检测 | 包含否定词对（如"喜欢"→"不喜欢"） | `REVERSAL` |
| 细化检测 | 新内容长度 > 旧内容 × 1.5 且语义包含 | `REFINEMENT` |
| 纠正检测 | 明确的错误修正语义 | `CORRECTION` |
| 更新检测 | 同一属性的值变化 | `UPDATE` |
| 默认 | 以上都不满足 | `EVOLUTION` |

---

## 6. 项目结构

```
memory-mcp/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
│
├── src/
│   └── memory_mcp/
│       ├── __init__.py
│       ├── __main__.py               # 入口点
│       ├── server.py                 # MCP Server 主逻辑
│       ├── config.py                 # 配置管理
│       │
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── streamable_http.py    # Streamable HTTP 实现
│       │   └── auth.py               # Token 认证中间件
│       │
│       ├── tools/                    # MCP Tools
│       │   ├── __init__.py
│       │   ├── remember.py
│       │   ├── recall.py
│       │   ├── trace.py
│       │   ├── forget.py
│       │   ├── relate.py
│       │   └── graph_query.py
│       │
│       ├── engine/                   # 核心引擎
│       │   ├── __init__.py
│       │   ├── models.py             # 数据模型
│       │   ├── conflict.py           # 冲突检测
│       │   ├── evolution.py          # 演化管理
│       │   └── embedding.py          # Embedding 服务
│       │
│       └── storage/                  # 存储层
│           ├── __init__.py
│           ├── vector.py             # LanceDB 操作
│           └── graph.py              # NetworkX + JSON 操作
│
├── tests/
│   ├── __init__.py
│   ├── test_remember.py
│   ├── test_recall.py
│   ├── test_evolution.py
│   └── conftest.py
│
└── data/                             # 数据目录（运行时生成）
    ├── vectors/
    └── graph/
```

---

## 7. 配置项

### 7.1 环境变量

```bash
# .env

# Server
MEMORY_MCP_HOST=0.0.0.0
MEMORY_MCP_PORT=8765
MEMORY_MCP_DEBUG=false

# Authentication
MEMORY_MCP_AUTH_TOKEN=your-secure-token-here

# Storage
MEMORY_MCP_DATA_DIR=/app/data

# Embedding (OpenRouter)
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIM=1536

# Conflict Detection (可选，用 Embedding 相似度可省略)
LLM_MODEL=anthropic/claude-3-haiku
```

### 7.2 配置类

```python
# src/memory_mcp/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8765
    debug: bool = False
    
    # Auth
    auth_token: str
    
    # Storage
    data_dir: str = "./data"
    
    # Embedding
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 1536
    
    # Conflict Detection
    similarity_threshold: float = 0.85
    llm_model: str = "anthropic/claude-3-haiku"
    
    class Config:
        env_prefix = "MEMORY_MCP_"
        env_file = ".env"

settings = Settings()
```

---

## 8. 部署方案

### 8.1 Docker Compose

```yaml
# docker-compose.yml

version: '3.8'

services:
  memory-mcp:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: memory-mcp
    restart: unless-stopped
    ports:
      - "8765:8765"
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env:ro
    environment:
      - MEMORY_MCP_HOST=0.0.0.0
      - MEMORY_MCP_PORT=8765
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8765/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: memory-mcp-tunnel
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
    environment:
      - CLOUDFLARE_TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      - memory-mcp
```

### 8.2 Dockerfile

```dockerfile
# Dockerfile

FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# 复制源码
COPY src/ src/

# 创建数据目录
RUN mkdir -p /app/data/vectors /app/data/graph

# 暴露端口
EXPOSE 8765

# 启动命令
CMD ["python", "-m", "memory_mcp"]
```

### 8.3 Cloudflare Tunnel 配置

**步骤**：

1. 登录 Cloudflare Zero Trust Dashboard
2. 创建新 Tunnel
3. 配置 Public Hostname：
   - Subdomain: `memory-mcp`
   - Domain: `your-domain.com`
   - Service: `http://memory-mcp:8765`
4. 复制 Tunnel Token 到 `.env`

**Tunnel Ingress 配置**（可选，在 Cloudflare Dashboard 配置）：
```yaml
ingress:
  - hostname: memory-mcp.your-domain.com
    service: http://memory-mcp:8765
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

### 8.4 部署命令

```bash
# 1. 克隆仓库
git clone <repo>
cd memory-mcp

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 tokens

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f memory-mcp

# 5. 验证服务
curl https://memory-mcp.your-domain.com/health
```

---

## 9. 客户端配置

### 9.1 MCP 客户端配置

```json
{
  "mcpServers": {
    "memory": {
      "url": "https://memory-mcp.your-domain.com/mcp",
      "transport": {
        "type": "http"
      },
      "headers": {
        "Authorization": "Bearer your-secure-token-here"
      }
    }
  }
}
```

### 9.2 Claude Desktop 配置

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://memory-mcp.your-domain.com/mcp",
        "--header",
        "Authorization: Bearer your-secure-token-here"
      ]
    }
  }
}
```

---

## 10. 依赖清单

### 10.1 pyproject.toml

```toml
[project]
name = "memory-mcp"
version = "1.0.0"
description = "Personal memory service with semantic search and knowledge graph"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "lancedb>=0.4.0",
    "pyarrow>=14.0.0",
    "networkx>=3.2.0",
    "numpy>=1.26.0",
    "uvicorn>=0.27.0",
    "starlette>=0.36.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.2.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/memory_mcp"]
```

---

## 11. API 示例

### 11.1 初始化会话

```http
POST /mcp HTTP/1.1
Host: memory-mcp.your-domain.com
Authorization: Bearer your-token
Content-Type: application/json
Accept: application/json, text/event-stream

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {
      "name": "my-client",
      "version": "1.0.0"
    }
  }
}
```

**响应**：
```http
HTTP/1.1 200 OK
Content-Type: application/json
Mcp-Session-Id: 550e8400-e29b-41d4-a716-446655440000

{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "tools": {}
    },
    "serverInfo": {
      "name": "memory-mcp",
      "version": "1.0.0"
    }
  }
}
```

### 11.2 调用 Tool

```http
POST /mcp HTTP/1.1
Host: memory-mcp.your-domain.com
Authorization: Bearer your-token
Mcp-Session-Id: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json
Accept: application/json, text/event-stream

{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "remember",
    "arguments": {
      "content": "偏好使用 Cursor 作为主要编辑器",
      "entity_type": "preference",
      "entity_key": "preference:editor"
    }
  }
}
```

---

## 12. 测试计划

### 12.1 单元测试

| 模块 | 测试点 |
|------|--------|
| `remember` | 新建记忆、演化触发、冲突检测 |
| `recall` | 语义检索准确性、过滤条件 |
| `trace` | 演化链完整性、顺序正确性 |
| `evolution` | 变更类型推断、原因生成 |
| `embedding` | API 调用、向量维度 |

### 12.2 集成测试

- 完整的记忆生命周期：创建 → 查询 → 演化 → 追溯
- 多实体关系图查询
- 会话管理与认证

### 12.3 性能指标

| 指标 | 目标 |
|------|------|
| 单次记忆写入 | < 500ms |
| 语义检索（1000条） | < 200ms |
| 演化链查询 | < 100ms |
| 并发支持 | 10 QPS |

---

## 13. 里程碑

| 阶段 | 内容 | 预期时间 |
|------|------|---------|
| **Phase 1: MVP** | 基础 remember/recall/trace，文件存储 | 1 周 |
| **Phase 2: 演化引擎** | 冲突检测、自动演化、变更原因 | 1 周 |
| **Phase 3: 图能力** | 关系管理、图查询 | 3 天 |
| **Phase 4: 部署** | Docker、Cloudflare Tunnel、文档 | 2 天 |
| **Phase 5: 优化** | 性能调优、测试完善 | 持续 |

---

## 14. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| OpenRouter API 不可用 | Embedding 失败 | 本地 fallback（Ollama） |
| 数据文件损坏 | 记忆丢失 | 定期备份、JSON 可读 |
| Token 泄露 | 未授权访问 | 定期轮换、监控告警 |
| 存储容量 | 服务降级 | 归档策略、监控告警 |

---

## 15. 未来扩展

- **多用户支持**：引入用户隔离与权限
- **多模态记忆**：支持图片、语音描述
- **自动摘要**：长期记忆压缩
- **记忆推理**：基于图结构的隐式知识推断
- **同步机制**：跨设备记忆同步

---

## 附录 A：术语表

| 术语 | 定义 |
|------|------|
| **MemoryNode** | 记忆的最小存储单元 |
| **Entity** | 记忆所属的实体（人、偏好、事件等） |
| **Evolution Chain** | 同一实体的记忆演化历史链 |
| **Mutation** | 记忆的一次变更 |
| **entity_key** | 实体的唯一标识符 |

---

## 附录 B：参考资料

- [MCP Specification 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [LanceDB Documentation](https://lancedb.github.io/lancedb/)
- [OpenRouter API](https://openrouter.ai/docs)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)