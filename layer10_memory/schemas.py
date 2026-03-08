from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Artifact(BaseModel):
    artifact_id: str
    corpus: str
    artifact_type: Literal[
        "issue", "issue_comment", "pull_request", "commit", "discussion"
    ]
    source_url: str
    created_at: datetime
    updated_at: datetime | None = None
    author: str | None = None
    title: str | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourcePointer(BaseModel):
    source_id: str
    artifact_id: str
    source_url: str
    excerpt: str
    char_start: int | None = None
    char_end: int | None = None
    observed_at: datetime

    @model_validator(mode="after")
    def validate_offsets(self) -> "SourcePointer":
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must both be set or both be None")
        if self.char_start is not None and self.char_end is not None:
            if self.char_start < 0 or self.char_end < self.char_start:
                raise ValueError("invalid offsets")
        return self


class Entity(BaseModel):
    entity_id: str
    entity_type: Literal[
        "person", "team", "repository", "issue", "pull_request", "component", "label"
    ]
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    external_refs: dict[str, str] = Field(default_factory=dict)
    confidence: float = 1.0


class Claim(BaseModel):
    claim_id: str
    claim_type: Literal[
        "issue_state",
        "assigned_to",
        "mentions_component",
        "mentions_label",
        "blocks",
        "decision",
        "action_item",
        "ownership_change",
    ]
    subject_entity_id: str
    object_entity_id: str | None = None
    value: str | None = None
    polarity: Literal["affirmed", "negated"] = "affirmed"
    confidence: float = 0.0
    event_time: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: Literal["current", "superseded", "conflicted"] = "current"
    evidence: list[SourcePointer] = Field(default_factory=list)
    extraction_version: str


class MergeOperation(BaseModel):
    operation_id: str
    merge_type: Literal["artifact", "entity", "claim"]
    winner_id: str
    loser_ids: list[str]
    reason: str
    score: float
    timestamp: datetime
    reversible: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryGraphSnapshot(BaseModel):
    schema_version: str
    generated_at: datetime
    corpus_id: str
    entities: list[Entity]
    claims: list[Claim]
    artifacts: list[Artifact]
    merges: list[MergeOperation]
