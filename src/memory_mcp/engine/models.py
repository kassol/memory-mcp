from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class MutationType(str, Enum):
    INITIAL = "initial"
    UPDATE = "update"
    REFINEMENT = "refinement"
    CORRECTION = "correction"
    REVERSAL = "reversal"
    EVOLUTION = "evolution"


class ReviewStatus(str, Enum):
    AUTO = "auto"
    REVIEWED = "reviewed"
    CONFIRMED = "confirmed"
    CHALLENGED = "challenged"
    LEGACY = "legacy"
    ARCHIVED = "archived"


class SourceRef(BaseModel):
    thread_id: str
    message_id: Optional[str] = None


class MemoryNode(BaseModel):
    # Identity
    id: str
    entity_key: str
    entity_type: str

    # Content (ε)
    content: str
    content_tokens: Optional[str] = None
    title: Optional[str] = None
    title_tokens: Optional[str] = None

    # Embedding (vector lives in LanceDB; kept in-memory for serialization)
    embedding: List[float] = Field(default_factory=list)

    # Evolution
    parent_id: Optional[str] = None
    mutation_type: MutationType
    mutation_reason: Optional[str] = None

    # Time
    created_at: datetime
    valid_from: datetime
    valid_until: Optional[datetime] = None

    # State
    is_current: bool
    confidence: float = 1.0
    review_status: ReviewStatus = ReviewStatus.AUTO  # α
    archived_reason: Optional[str] = None
    archived_at: Optional[datetime] = None
    conflict: bool = False
    conflict_with_id: Optional[str] = None

    # Metadata
    tags: List[str] = Field(default_factory=list)
    source: str = "conversation"
    origin_client: Optional[str] = None         # β
    origin_session_id: Optional[str] = None     # β

    # Source linkage (γ)
    source_thread_id: Optional[str] = None
    source_refs: List[SourceRef] = Field(default_factory=list)

    # Access stats (δ)
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    reinforce_count: int = 0


class Entity(BaseModel):
    entity_key: str
    name: Optional[str] = None
    entity_type: str
    current_memory_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Relation(BaseModel):
    id: str
    from_entity_key: str
    to_entity_key: str
    relation_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
