from __future__ import annotations

import re
from collections.abc import Iterable

from layer10_memory.config import EXTRACTION_VERSION
from layer10_memory.extraction.contract import BaseExtractor, ExtractionResult
from layer10_memory.schemas import Artifact, Claim, Entity, SourcePointer
from layer10_memory.utils import (
    canonical_person_name,
    normalize_text,
    safe_excerpt,
    stable_id,
)

MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9][A-Za-z0-9\-]{0,38})")
ISSUE_REF_RE = re.compile(r"(?<!\w)#(\d{1,7})")
COMPONENT_RE = re.compile(r"\b(component|module|area)\s*[:=]\s*([A-Za-z0-9_\-/]+)", re.I)
DECISION_RE = re.compile(r"\b(decision|decided|resolved|final call)\b", re.I)
ACTION_RE = re.compile(r"\b(action item|todo|next step|follow up|i will|we will|please)\b", re.I)
BLOCK_RE = re.compile(r"\b(blocked by|blocks|depends on|wait for)\b", re.I)


class HeuristicExtractor(BaseExtractor):
    name = "heuristic"
    version = "1.0.0"

    def extract(self, artifact: Artifact) -> ExtractionResult:
        entities: dict[str, Entity] = {}
        claims: list[Claim] = []

        repo = str(artifact.metadata.get("repository", "unknown/unknown"))
        issue_number = str(artifact.metadata.get("issue_number", "unknown"))

        repo_entity = self._upsert_entity(
            entities,
            entity_type="repository",
            canonical_name=repo,
            external_refs={"repository": repo},
            confidence=1.0,
        )

        issue_entity = self._upsert_entity(
            entities,
            entity_type="issue",
            canonical_name=f"{repo}#{issue_number}",
            external_refs={"repository": repo, "issue_number": issue_number},
            confidence=1.0,
        )

        if artifact.author:
            author = canonical_person_name(artifact.author)
            self._upsert_entity(
                entities,
                entity_type="person",
                canonical_name=author,
                aliases=[artifact.author],
                confidence=0.98,
            )

        for mention in MENTION_RE.finditer(artifact.text):
            username = canonical_person_name(mention.group(1))
            self._upsert_entity(
                entities,
                entity_type="person",
                canonical_name=username,
                aliases=[mention.group(1)],
                confidence=0.85,
            )

        for label in artifact.metadata.get("labels", []):
            label_norm = normalize_text(label)
            if not label_norm:
                continue
            label_entity = self._upsert_entity(
                entities,
                entity_type="label",
                canonical_name=label_norm,
                aliases=[label],
                confidence=0.95,
            )
            claims.append(
                Claim(
                    claim_id=stable_id(
                        "clm", artifact.artifact_id, "mentions_label", issue_entity.entity_id, label_entity.entity_id
                    ),
                    claim_type="mentions_label",
                    subject_entity_id=issue_entity.entity_id,
                    object_entity_id=label_entity.entity_id,
                    confidence=0.97,
                    event_time=artifact.updated_at or artifact.created_at,
                    valid_from=artifact.created_at,
                    evidence=[
                        self._evidence_from_text(
                            artifact,
                            f"label:{label}",
                            char_start=None,
                            char_end=None,
                        )
                    ],
                    extraction_version=EXTRACTION_VERSION,
                )
            )

        for assignee in artifact.metadata.get("assignees", []):
            assignee_norm = canonical_person_name(assignee)
            person = self._upsert_entity(
                entities,
                entity_type="person",
                canonical_name=assignee_norm,
                aliases=[assignee],
                confidence=0.92,
            )
            claims.append(
                Claim(
                    claim_id=stable_id(
                        "clm",
                        artifact.artifact_id,
                        "assigned_to",
                        issue_entity.entity_id,
                        person.entity_id,
                    ),
                    claim_type="assigned_to",
                    subject_entity_id=issue_entity.entity_id,
                    object_entity_id=person.entity_id,
                    confidence=0.92,
                    event_time=artifact.updated_at or artifact.created_at,
                    valid_from=artifact.created_at,
                    evidence=[
                        self._evidence_from_text(
                            artifact,
                            f"assignee:{assignee}",
                            char_start=None,
                            char_end=None,
                        )
                    ],
                    extraction_version=EXTRACTION_VERSION,
                )
            )

        state = artifact.metadata.get("state")
        if state:
            claims.append(
                Claim(
                    claim_id=stable_id("clm", artifact.artifact_id, "issue_state", issue_entity.entity_id, state),
                    claim_type="issue_state",
                    subject_entity_id=issue_entity.entity_id,
                    value=str(state),
                    confidence=1.0,
                    event_time=artifact.updated_at or artifact.created_at,
                    valid_from=artifact.created_at,
                    evidence=[
                        self._evidence_from_text(
                            artifact,
                            f"state:{state}",
                            char_start=None,
                            char_end=None,
                        )
                    ],
                    extraction_version=EXTRACTION_VERSION,
                )
            )

        for comp in COMPONENT_RE.finditer(artifact.text):
            component = normalize_text(comp.group(2))
            if not component:
                continue
            component_entity = self._upsert_entity(
                entities,
                entity_type="component",
                canonical_name=component,
                aliases=[comp.group(2)],
                confidence=0.78,
            )
            claims.append(
                Claim(
                    claim_id=stable_id(
                        "clm",
                        artifact.artifact_id,
                        "mentions_component",
                        issue_entity.entity_id,
                        component_entity.entity_id,
                        str(comp.span()),
                    ),
                    claim_type="mentions_component",
                    subject_entity_id=issue_entity.entity_id,
                    object_entity_id=component_entity.entity_id,
                    confidence=0.78,
                    event_time=artifact.created_at,
                    valid_from=artifact.created_at,
                    evidence=[
                        self._evidence_from_text(
                            artifact,
                            comp.group(0),
                            comp.start(),
                            comp.end(),
                        )
                    ],
                    extraction_version=EXTRACTION_VERSION,
                )
            )

        for sentence in self._sentences(artifact.text):
            if DECISION_RE.search(sentence["text"]):
                claims.append(
                    Claim(
                        claim_id=stable_id(
                            "clm",
                            artifact.artifact_id,
                            "decision",
                            issue_entity.entity_id,
                            sentence["text"],
                        ),
                        claim_type="decision",
                        subject_entity_id=issue_entity.entity_id,
                        value=sentence["text"][:400],
                        confidence=0.72,
                        event_time=artifact.created_at,
                        valid_from=artifact.created_at,
                        evidence=[
                            self._evidence_from_text(
                                artifact,
                                sentence["text"],
                                sentence["start"],
                                sentence["end"],
                            )
                        ],
                        extraction_version=EXTRACTION_VERSION,
                    )
                )
            if ACTION_RE.search(sentence["text"]):
                claims.append(
                    Claim(
                        claim_id=stable_id(
                            "clm",
                            artifact.artifact_id,
                            "action_item",
                            issue_entity.entity_id,
                            sentence["text"],
                        ),
                        claim_type="action_item",
                        subject_entity_id=issue_entity.entity_id,
                        value=sentence["text"][:400],
                        confidence=0.68,
                        event_time=artifact.created_at,
                        valid_from=artifact.created_at,
                        evidence=[
                            self._evidence_from_text(
                                artifact,
                                sentence["text"],
                                sentence["start"],
                                sentence["end"],
                            )
                        ],
                        extraction_version=EXTRACTION_VERSION,
                    )
                )

        if BLOCK_RE.search(artifact.text):
            for ref in ISSUE_REF_RE.finditer(artifact.text):
                target_entity = self._upsert_entity(
                    entities,
                    entity_type="issue",
                    canonical_name=f"{repo}#{ref.group(1)}",
                    external_refs={"repository": repo, "issue_number": ref.group(1)},
                    confidence=0.8,
                )
                claims.append(
                    Claim(
                        claim_id=stable_id(
                            "clm",
                            artifact.artifact_id,
                            "blocks",
                            issue_entity.entity_id,
                            target_entity.entity_id,
                            str(ref.span()),
                        ),
                        claim_type="blocks",
                        subject_entity_id=issue_entity.entity_id,
                        object_entity_id=target_entity.entity_id,
                        confidence=0.7,
                        event_time=artifact.created_at,
                        valid_from=artifact.created_at,
                        evidence=[
                            self._evidence_from_text(
                                artifact,
                                ref.group(0),
                                ref.start(),
                                ref.end(),
                            )
                        ],
                        extraction_version=EXTRACTION_VERSION,
                    )
                )

        # lightweight relation claim to keep repository linkage explicit
        claims.append(
            Claim(
                claim_id=stable_id(
                    "clm",
                    artifact.artifact_id,
                    "mentions_component",
                    issue_entity.entity_id,
                    repo_entity.entity_id,
                    "repo-link",
                ),
                claim_type="mentions_component",
                subject_entity_id=issue_entity.entity_id,
                object_entity_id=repo_entity.entity_id,
                value="repository_link",
                confidence=1.0,
                event_time=artifact.created_at,
                valid_from=artifact.created_at,
                evidence=[self._evidence_from_text(artifact, artifact.title or artifact.text[:120], None, None)],
                extraction_version=EXTRACTION_VERSION,
            )
        )

        return ExtractionResult(
            artifact=artifact,
            entities=list(entities.values()),
            claims=claims,
        )

    @staticmethod
    def _sentences(text: str) -> Iterable[dict[str, int | str]]:
        chunks = re.split(r"(?<=[.!?])\s+", text)
        cursor = 0
        for chunk in chunks:
            stripped = chunk.strip()
            if not stripped:
                cursor += len(chunk) + 1
                continue
            start = text.find(stripped, cursor)
            end = start + len(stripped)
            cursor = end
            yield {"text": stripped, "start": start, "end": end}

    @staticmethod
    def _upsert_entity(
        entities: dict[str, Entity],
        entity_type: str,
        canonical_name: str,
        aliases: list[str] | None = None,
        external_refs: dict[str, str] | None = None,
        confidence: float = 1.0,
    ) -> Entity:
        aliases = aliases or []
        external_refs = external_refs or {}
        canonical = normalize_text(canonical_name)
        entity_id = stable_id("ent", entity_type, canonical)

        if entity_id in entities:
            existing = entities[entity_id]
            existing.aliases = sorted({*existing.aliases, *aliases})
            existing.external_refs = {**existing.external_refs, **external_refs}
            existing.confidence = max(existing.confidence, confidence)
            return existing

        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical,
            aliases=sorted(set(aliases)),
            external_refs=external_refs,
            confidence=confidence,
        )
        entities[entity_id] = entity
        return entity

    @staticmethod
    def _evidence_from_text(
        artifact: Artifact,
        needle: str,
        char_start: int | None,
        char_end: int | None,
    ) -> SourcePointer:
        text = artifact.text or ""
        start = char_start
        end = char_end

        if start is None or end is None:
            idx = text.lower().find((needle or "").lower())
            if idx >= 0:
                start = idx
                end = idx + len(needle)

        excerpt = safe_excerpt(text, start, end)
        return SourcePointer(
            source_id=stable_id("src", artifact.artifact_id, str(start), str(end), needle[:64]),
            artifact_id=artifact.artifact_id,
            source_url=artifact.source_url,
            excerpt=excerpt,
            char_start=start,
            char_end=end,
            observed_at=artifact.updated_at or artifact.created_at,
        )
