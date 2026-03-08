from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from rank_bm25 import BM25Okapi

from layer10_memory.schemas import Claim, Entity, MemoryGraphSnapshot
from layer10_memory.utils import normalize_text


@dataclass
class RankedClaim:
    claim: Claim
    score: float



def build_context_pack(
    snapshot: MemoryGraphSnapshot,
    question: str,
    top_k: int = 8,
    include_conflicts: bool = True,
) -> dict[str, Any]:
    entity_by_id = {entity.entity_id: entity for entity in snapshot.entities}
    if not snapshot.claims:
        return {
            "question": question,
            "retrieved_at": datetime.now(tz=UTC).isoformat(),
            "claims": [],
            "entities": [],
            "citations": [],
            "conflicts": [],
            "policy": {
                "grounding": "All returned claims include direct evidence excerpts and source URLs",
                "ambiguity": "Conflicted claims are included with status=conflicted",
            },
        }

    claim_docs = [_claim_document(claim, entity_by_id) for claim in snapshot.claims]
    corpus_tokens = [doc.split() for doc in claim_docs]
    bm25 = BM25Okapi(corpus_tokens)

    question_tokens = normalize_text(question).split()
    scores = bm25.get_scores(question_tokens)

    matched_entities = _entity_hits(snapshot.entities, question_tokens)

    ranked: list[RankedClaim] = []
    for claim, bm25_score in zip(snapshot.claims, scores, strict=True):
        boost = 0.0
        if claim.subject_entity_id in matched_entities:
            boost += 2.0
        if claim.object_entity_id and claim.object_entity_id in matched_entities:
            boost += 1.5
        boost += max(0.0, claim.confidence - 0.5)

        if claim.status == "conflicted":
            boost += 0.3

        ranked.append(RankedClaim(claim=claim, score=float(bm25_score) + boost))

    ranked.sort(key=lambda item: item.score, reverse=True)
    selected = _diverse_selection(ranked, top_k=top_k)

    entities: dict[str, dict[str, Any]] = {}
    context_claims: list[dict[str, Any]] = []
    citations: dict[str, dict[str, Any]] = {}

    for ranked_claim in selected:
        claim = ranked_claim.claim
        subject = entity_by_id.get(claim.subject_entity_id)
        object_entity = entity_by_id.get(claim.object_entity_id) if claim.object_entity_id else None

        if subject:
            entities[subject.entity_id] = {
                "entity_id": subject.entity_id,
                "entity_type": subject.entity_type,
                "canonical_name": subject.canonical_name,
                "aliases": subject.aliases,
            }
        if object_entity:
            entities[object_entity.entity_id] = {
                "entity_id": object_entity.entity_id,
                "entity_type": object_entity.entity_type,
                "canonical_name": object_entity.canonical_name,
                "aliases": object_entity.aliases,
            }

        evidence_payload = []
        for evidence in claim.evidence[:3]:
            evidence_payload.append(
                {
                    "source_id": evidence.source_id,
                    "artifact_id": evidence.artifact_id,
                    "source_url": evidence.source_url,
                    "excerpt": evidence.excerpt,
                    "char_start": evidence.char_start,
                    "char_end": evidence.char_end,
                    "observed_at": evidence.observed_at.isoformat(),
                }
            )
            citations[evidence.source_id] = {
                "source_id": evidence.source_id,
                "artifact_id": evidence.artifact_id,
                "source_url": evidence.source_url,
                "excerpt": evidence.excerpt,
            }

        context_claims.append(
            {
                "claim_id": claim.claim_id,
                "claim_type": claim.claim_type,
                "subject": subject.canonical_name if subject else claim.subject_entity_id,
                "object": object_entity.canonical_name if object_entity else claim.value,
                "status": claim.status,
                "confidence": claim.confidence,
                "score": ranked_claim.score,
                "event_time": claim.event_time.isoformat() if claim.event_time else None,
                "valid_from": claim.valid_from.isoformat() if claim.valid_from else None,
                "valid_to": claim.valid_to.isoformat() if claim.valid_to else None,
                "evidence": evidence_payload,
            }
        )

    conflicts = _conflict_summary(snapshot.claims, entity_by_id) if include_conflicts else []

    return {
        "question": question,
        "retrieved_at": datetime.now(tz=UTC).isoformat(),
        "claims": context_claims,
        "entities": list(entities.values()),
        "citations": list(citations.values()),
        "conflicts": conflicts,
        "policy": {
            "grounding": "All returned claims include direct evidence excerpts and source URLs",
            "ambiguity": "Conflicted claims are included with status=conflicted",
        },
    }



def _claim_document(claim: Claim, entity_by_id: dict[str, Entity]) -> str:
    subject = entity_by_id.get(claim.subject_entity_id)
    object_entity = entity_by_id.get(claim.object_entity_id) if claim.object_entity_id else None
    values = [
        claim.claim_type,
        subject.canonical_name if subject else claim.subject_entity_id,
        object_entity.canonical_name if object_entity else (claim.value or ""),
        claim.status,
        " ".join(ev.excerpt for ev in claim.evidence[:2]),
    ]
    return normalize_text(" ".join(values))



def _entity_hits(entities: list[Entity], question_tokens: list[str]) -> set[str]:
    hits: set[str] = set()
    question_set = set(question_tokens)
    for entity in entities:
        cand_tokens = set(normalize_text(entity.canonical_name).split())
        alias_tokens = set()
        for alias in entity.aliases:
            alias_tokens |= set(normalize_text(alias).split())
        if question_set & (cand_tokens | alias_tokens):
            hits.add(entity.entity_id)
    return hits



def _diverse_selection(ranked: list[RankedClaim], top_k: int) -> list[RankedClaim]:
    selected: list[RankedClaim] = []
    seen_claim_types: dict[str, int] = defaultdict(int)

    for item in ranked:
        if len(selected) >= top_k:
            break
        ctype = item.claim.claim_type
        if seen_claim_types[ctype] >= max(1, top_k // 3):
            continue
        selected.append(item)
        seen_claim_types[ctype] += 1

    if len(selected) < top_k:
        for item in ranked:
            if len(selected) >= top_k:
                break
            if item in selected:
                continue
            selected.append(item)

    return selected



def _conflict_summary(claims: list[Claim], entity_by_id: dict[str, Entity]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for claim in claims:
        if claim.status in {"conflicted", "superseded"}:
            grouped[(claim.subject_entity_id, claim.claim_type)].append(claim)

    summary = []
    for (subject_id, claim_type), group in grouped.items():
        subject = entity_by_id.get(subject_id)
        summary.append(
            {
                "subject": subject.canonical_name if subject else subject_id,
                "claim_type": claim_type,
                "variants": [
                    {
                        "claim_id": claim.claim_id,
                        "value": claim.value or claim.object_entity_id,
                        "status": claim.status,
                        "confidence": claim.confidence,
                    }
                    for claim in group
                ],
            }
        )

    return summary
