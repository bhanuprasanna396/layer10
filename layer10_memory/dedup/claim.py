from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from layer10_memory.schemas import Claim, MergeOperation
from layer10_memory.utils import normalize_text, stable_id



def deduplicate_and_resolve_claims(
    claims: list[Claim],
    entity_id_map: dict[str, str],
) -> tuple[list[Claim], list[MergeOperation]]:
    keyed: dict[str, Claim] = {}
    merges: list[MergeOperation] = []

    for claim in claims:
        claim.subject_entity_id = entity_id_map.get(claim.subject_entity_id, claim.subject_entity_id)
        if claim.object_entity_id:
            claim.object_entity_id = entity_id_map.get(claim.object_entity_id, claim.object_entity_id)

        key = _claim_key(claim)
        if key not in keyed:
            keyed[key] = claim
            continue

        winner = keyed[key]
        winner.evidence.extend(claim.evidence)
        winner.confidence = max(winner.confidence, claim.confidence)
        winner.valid_from = min(
            [dt for dt in [winner.valid_from, claim.valid_from] if dt is not None],
            default=winner.valid_from,
        )
        winner.valid_to = max(
            [dt for dt in [winner.valid_to, claim.valid_to] if dt is not None],
            default=winner.valid_to,
        )

        merges.append(
            MergeOperation(
                operation_id=stable_id("mrg", "claim", winner.claim_id, claim.claim_id),
                merge_type="claim",
                winner_id=winner.claim_id,
                loser_ids=[claim.claim_id],
                reason="semantic_claim_key_match",
                score=0.98,
                timestamp=datetime.now(tz=UTC),
            )
        )

    merged_claims = list(keyed.values())
    _resolve_temporal_conflicts(merged_claims)
    _dedup_evidence(merged_claims)
    return merged_claims, merges



def _claim_key(claim: Claim) -> str:
    return "|".join(
        [
            claim.claim_type,
            claim.subject_entity_id,
            claim.object_entity_id or "",
            normalize_text(claim.value or ""),
            claim.polarity,
        ]
    )



def _resolve_temporal_conflicts(claims: list[Claim]) -> None:
    by_subject_type: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for claim in claims:
        by_subject_type[(claim.subject_entity_id, claim.claim_type)].append(claim)

    temporal_claim_types = {"issue_state", "assigned_to", "ownership_change"}

    for (subject_id, claim_type), group in by_subject_type.items():
        if claim_type not in temporal_claim_types or len(group) <= 1:
            continue

        group.sort(key=lambda c: c.event_time or c.valid_from or datetime(1970, 1, 1, tzinfo=UTC))

        latest = group[-1]
        latest.status = "current"
        latest.valid_to = None

        for older in group[:-1]:
            changed = (older.value or older.object_entity_id) != (latest.value or latest.object_entity_id)
            if changed:
                older.status = "superseded"
                older.valid_to = latest.event_time or latest.valid_from or older.valid_to
            else:
                older.status = "current"

        # if latest disagrees with multiple recent sources, mark as conflicted
        distinct_values = {c.value or c.object_entity_id for c in group[-3:]}
        if len(distinct_values) > 1:
            latest.status = "conflicted"
            latest.valid_to = None



def _dedup_evidence(claims: list[Claim]) -> None:
    for claim in claims:
        unique = {e.source_id: e for e in claim.evidence}
        claim.evidence = list(unique.values())
