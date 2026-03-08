from __future__ import annotations

from datetime import UTC, datetime

from rapidfuzz import fuzz

from layer10_memory.schemas import Entity, MergeOperation
from layer10_memory.utils import canonical_person_name, normalize_text, stable_id



def canonicalize_entities(
    entities: list[Entity],
    alias_threshold: int = 93,
) -> tuple[list[Entity], list[MergeOperation], dict[str, str]]:
    canonical: dict[str, Entity] = {}
    merges: list[MergeOperation] = []
    id_map: dict[str, str] = {}

    for entity in entities:
        key = f"{entity.entity_type}:{normalize_text(entity.canonical_name)}"
        if key in canonical:
            winner = canonical[key]
            _merge_entity(winner, entity)
            merges.append(
                MergeOperation(
                    operation_id=stable_id("mrg", "entity", winner.entity_id, entity.entity_id),
                    merge_type="entity",
                    winner_id=winner.entity_id,
                    loser_ids=[entity.entity_id],
                    reason="exact_canonical_match",
                    score=1.0,
                    timestamp=datetime.now(tz=UTC),
                )
            )
            id_map[entity.entity_id] = winner.entity_id
            continue

        fuzzy_winner = _find_alias_match(entity, canonical.values(), alias_threshold)
        if fuzzy_winner:
            _merge_entity(fuzzy_winner, entity)
            score = fuzz.ratio(
                canonical_person_name(entity.canonical_name),
                canonical_person_name(fuzzy_winner.canonical_name),
            ) / 100.0
            merges.append(
                MergeOperation(
                    operation_id=stable_id("mrg", "entity", fuzzy_winner.entity_id, entity.entity_id),
                    merge_type="entity",
                    winner_id=fuzzy_winner.entity_id,
                    loser_ids=[entity.entity_id],
                    reason="alias_similarity",
                    score=score,
                    timestamp=datetime.now(tz=UTC),
                )
            )
            id_map[entity.entity_id] = fuzzy_winner.entity_id
            continue

        canonical[key] = entity
        id_map[entity.entity_id] = entity.entity_id

    return list(canonical.values()), merges, id_map



def _merge_entity(winner: Entity, loser: Entity) -> None:
    winner.aliases = sorted(set(winner.aliases + loser.aliases + [loser.canonical_name]))
    winner.external_refs = {**loser.external_refs, **winner.external_refs}
    winner.confidence = max(winner.confidence, loser.confidence)



def _find_alias_match(
    candidate: Entity,
    existing: list[Entity] | tuple[Entity, ...] | set[Entity] | object,
    threshold: int,
) -> Entity | None:
    if candidate.entity_type not in {"person", "team"}:
        return None

    candidate_name = canonical_person_name(candidate.canonical_name)
    for entity in existing:  # type: ignore[assignment]
        if not isinstance(entity, Entity):
            continue
        if entity.entity_type != candidate.entity_type:
            continue
        score = fuzz.ratio(candidate_name, canonical_person_name(entity.canonical_name))
        if score >= threshold:
            return entity

    return None
