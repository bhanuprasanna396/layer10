from __future__ import annotations

from datetime import UTC, datetime

from rapidfuzz import fuzz

from layer10_memory.schemas import Artifact, MergeOperation
from layer10_memory.utils import normalize_text, stable_id



def deduplicate_artifacts(
    artifacts: list[Artifact],
    near_duplicate_threshold: int = 96,
) -> tuple[list[Artifact], list[MergeOperation], dict[str, str]]:
    exact_index: dict[str, str] = {}
    kept: dict[str, Artifact] = {}
    merges: list[MergeOperation] = []
    canonical_map: dict[str, str] = {}

    artifacts_sorted = sorted(artifacts, key=lambda a: (a.created_at, a.artifact_id))

    for artifact in artifacts_sorted:
        text_key = normalize_text(artifact.text)
        key = stable_id("txt", text_key)

        if key in exact_index:
            winner_id = exact_index[key]
            merges.append(
                MergeOperation(
                    operation_id=stable_id("mrg", "artifact", winner_id, artifact.artifact_id),
                    merge_type="artifact",
                    winner_id=winner_id,
                    loser_ids=[artifact.artifact_id],
                    reason="exact_text_match",
                    score=1.0,
                    timestamp=datetime.now(tz=UTC),
                    metadata={
                        "winner_source": kept[winner_id].source_url,
                        "loser_source": artifact.source_url,
                    },
                )
            )
            canonical_map[artifact.artifact_id] = winner_id
            continue

        near_winner = _find_near_duplicate(artifact, kept.values(), near_duplicate_threshold)
        if near_winner:
            winner_id = near_winner.artifact_id
            score = fuzz.ratio(normalize_text(artifact.text), normalize_text(near_winner.text)) / 100.0
            merges.append(
                MergeOperation(
                    operation_id=stable_id("mrg", "artifact", winner_id, artifact.artifact_id),
                    merge_type="artifact",
                    winner_id=winner_id,
                    loser_ids=[artifact.artifact_id],
                    reason="near_text_match",
                    score=score,
                    timestamp=datetime.now(tz=UTC),
                    metadata={
                        "winner_source": near_winner.source_url,
                        "loser_source": artifact.source_url,
                        "issue_number": artifact.metadata.get("issue_number"),
                    },
                )
            )
            canonical_map[artifact.artifact_id] = winner_id
            continue

        exact_index[key] = artifact.artifact_id
        kept[artifact.artifact_id] = artifact
        canonical_map[artifact.artifact_id] = artifact.artifact_id

    return list(kept.values()), merges, canonical_map



def _find_near_duplicate(
    candidate: Artifact,
    existing: list[Artifact] | tuple[Artifact, ...] | set[Artifact] | object,
    threshold: int,
) -> Artifact | None:
    candidate_key = normalize_text(candidate.text)
    issue_number = candidate.metadata.get("issue_number")

    for artifact in existing:  # type: ignore[assignment]
        if not isinstance(artifact, Artifact):
            continue
        if artifact.metadata.get("issue_number") != issue_number:
            continue
        if abs(len(artifact.text) - len(candidate.text)) > 200:
            continue

        score = fuzz.ratio(candidate_key, normalize_text(artifact.text))
        if score >= threshold:
            return artifact

    return None
