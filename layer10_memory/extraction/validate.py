from __future__ import annotations

from collections import defaultdict

from layer10_memory.schemas import Claim, Entity


class ValidationSummary:
    def __init__(self) -> None:
        self.invalid_claims = 0
        self.repaired_claims = 0



def validate_and_repair(
    entities: list[Entity],
    claims: list[Claim],
    min_confidence: float = 0.5,
) -> tuple[list[Entity], list[Claim], ValidationSummary]:
    summary = ValidationSummary()
    entity_ids = {entity.entity_id for entity in entities}

    merged: dict[str, Claim] = {}
    evidence_by_claim = defaultdict(list)

    for claim in claims:
        if claim.subject_entity_id not in entity_ids:
            summary.invalid_claims += 1
            continue
        if claim.object_entity_id and claim.object_entity_id not in entity_ids:
            summary.invalid_claims += 1
            continue
        if not claim.evidence:
            summary.invalid_claims += 1
            continue

        confidence = max(0.0, min(claim.confidence, 1.0))
        if confidence != claim.confidence:
            claim.confidence = confidence
            summary.repaired_claims += 1

        if claim.confidence < min_confidence:
            summary.invalid_claims += 1
            continue

        if claim.claim_id not in merged:
            merged[claim.claim_id] = claim
        evidence_by_claim[claim.claim_id].extend(claim.evidence)

    repaired_claims: list[Claim] = []
    for claim_id, claim in merged.items():
        dedup_evidence = {e.source_id: e for e in evidence_by_claim[claim_id]}
        claim.evidence = list(dedup_evidence.values())
        repaired_claims.append(claim)

    dedup_entities = {entity.entity_id: entity for entity in entities}
    return list(dedup_entities.values()), repaired_claims, summary
