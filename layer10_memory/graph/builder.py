from __future__ import annotations

import networkx as nx

from layer10_memory.schemas import MemoryGraphSnapshot



def build_memory_graph(snapshot: MemoryGraphSnapshot) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()

    for artifact in snapshot.artifacts:
        graph.add_node(
            artifact.artifact_id,
            kind="artifact",
            artifact_type=artifact.artifact_type,
            source_url=artifact.source_url,
            created_at=artifact.created_at.isoformat(),
            text=artifact.text,
            title=artifact.title,
            metadata=artifact.metadata,
        )

    for entity in snapshot.entities:
        graph.add_node(
            entity.entity_id,
            kind="entity",
            entity_type=entity.entity_type,
            canonical_name=entity.canonical_name,
            aliases=entity.aliases,
            confidence=entity.confidence,
            external_refs=entity.external_refs,
        )

    for claim in snapshot.claims:
        graph.add_node(
            claim.claim_id,
            kind="claim",
            claim_type=claim.claim_type,
            value=claim.value,
            polarity=claim.polarity,
            confidence=claim.confidence,
            status=claim.status,
            event_time=claim.event_time.isoformat() if claim.event_time else None,
            valid_from=claim.valid_from.isoformat() if claim.valid_from else None,
            valid_to=claim.valid_to.isoformat() if claim.valid_to else None,
            extraction_version=claim.extraction_version,
        )

        graph.add_edge(claim.subject_entity_id, claim.claim_id, relation="subject_of")

        if claim.object_entity_id:
            graph.add_edge(claim.claim_id, claim.object_entity_id, relation="object_of")

        for evidence in claim.evidence:
            graph.add_edge(
                claim.claim_id,
                evidence.artifact_id,
                relation="supported_by",
                source_id=evidence.source_id,
                excerpt=evidence.excerpt,
                source_url=evidence.source_url,
                char_start=evidence.char_start,
                char_end=evidence.char_end,
                observed_at=evidence.observed_at.isoformat(),
            )

    for merge in snapshot.merges:
        graph.add_node(
            merge.operation_id,
            kind="merge",
            merge_type=merge.merge_type,
            reason=merge.reason,
            score=merge.score,
            timestamp=merge.timestamp.isoformat(),
            reversible=merge.reversible,
            metadata=merge.metadata,
        )
        graph.add_edge(merge.operation_id, merge.winner_id, relation="winner")
        for loser_id in merge.loser_ids:
            graph.add_edge(merge.operation_id, loser_id, relation="loser")

    return graph
