from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

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
    parent_id: Optional[str] = None       # 前一版本节点 ID（None = 初始记忆）
    mutation_type: MutationType           # 变更类型
    mutation_reason: Optional[str] = None # 变更原因/触发事件描述
    
    # 时间
    created_at: datetime                  # 创建时间
    valid_from: datetime                  # 生效时间
    valid_until: Optional[datetime] = None # 失效时间（None = 当前有效）
    
    # 状态
    is_current: bool                      # 是否为最新状态
    confidence: float = 1.0               # 置信度 0-1
    archived_reason: Optional[str] = None # 归档原因
    archived_at: Optional[datetime] = None # 归档时间
    conflict: bool = False                # 是否检测到冲突/矛盾
    conflict_with_id: Optional[str] = None # 冲突来源节点（上一版本/相似节点）
    
    # 元数据
    tags: List[str] = Field(default_factory=list) # 标签
    source: str = "conversation"          # 来源：conversation | import | inference

class Entity(BaseModel):
    id: str
    name: str                             # 人类可读名称
    entity_key: str                       # 唯一标识
    entity_type: str
    current_memory_id: Optional[str] = None # 当前最新记忆节点
    created_at: datetime
    updated_at: datetime

class Relation(BaseModel):
    id: str
    from_entity_key: str
    to_entity_key: str
    relation_type: str                    # KNOWS | PREFERS | WORKS_ON | RELATED_TO 等
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
