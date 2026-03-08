#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from layer10_memory.config import SCHEMA_VERSION
from layer10_memory.corpus.github import github_to_artifacts, load_github_corpus
from layer10_memory.dedup.artifact import deduplicate_artifacts
from layer10_memory.dedup.claim import deduplicate_and_resolve_claims
from layer10_memory.dedup.entity import canonicalize_entities
from layer10_memory.extraction.contract import BaseExtractor
from layer10_memory.extraction.heuristic import HeuristicExtractor
from layer10_memory.extraction.ollama import OllamaExtractor
from layer10_memory.extraction.validate import validate_and_repair
from layer10_memory.graph.builder import build_memory_graph
from layer10_memory.graph.store import save_graph_json, save_snapshot
from layer10_memory.retrieval.context_pack import build_context_pack
from layer10_memory.schemas import Claim, Entity, MemoryGraphSnapshot, MergeOperation



def _build_extractor(name: str, model: str) -> BaseExtractor:
    if name == "ollama":
        return OllamaExtractor(model=model)
    return HeuristicExtractor()



def main() -> None:
    parser = argparse.ArgumentParser(description="Build memory graph snapshot from GitHub issues corpus")
    parser.add_argument("--input", default="data/raw/github_corpus.json", help="Input corpus JSON")
    parser.add_argument("--extractor", choices=["heuristic", "ollama"], default="heuristic")
    parser.add_argument("--model", default="qwen2.5:3b", help="Ollama model name")
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--snapshot-out", default="outputs/memory_snapshot.json")
    parser.add_argument("--graph-out", default="outputs/memory_graph.json")
    parser.add_argument("--context-out", default="outputs/context_packs.json")
    args = parser.parse_args()

    payload = load_github_corpus(args.input)
    artifacts = github_to_artifacts(payload)

    artifacts, artifact_merges, artifact_canonical_map = deduplicate_artifacts(artifacts)

    extractor = _build_extractor(args.extractor, args.model)

    all_entities: list[Entity] = []
    all_claims: list[Claim] = []
    extraction_warnings: list[str] = []

    for artifact in artifacts:
        result = extractor.extract(artifact)
        all_entities.extend(result.entities)
        all_claims.extend(result.claims)
        extraction_warnings.extend(result.warnings)

    entities, claims, validation_summary = validate_and_repair(
        all_entities,
        all_claims,
        min_confidence=args.min_confidence,
    )

    entities, entity_merges, entity_id_map = canonicalize_entities(entities)
    claims, claim_merges = deduplicate_and_resolve_claims(claims, entity_id_map=entity_id_map)

    merges: list[MergeOperation] = artifact_merges + entity_merges + claim_merges

    snapshot = MemoryGraphSnapshot(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(tz=UTC),
        corpus_id=payload.get("corpus_id", payload.get("repository", "unknown")),
        entities=entities,
        claims=claims,
        artifacts=artifacts,
        merges=merges,
    )

    save_snapshot(snapshot, args.snapshot_out)

    graph = build_memory_graph(snapshot)
    save_graph_json(graph, args.graph_out)

    repo = payload.get("repository", "repository")
    default_questions = [
        f"What is the current status of issues in {repo}?",
        f"What decisions were made recently in {repo}?",
        f"Who owns or is assigned to active work in {repo}?",
    ]

    context_packs = [build_context_pack(snapshot, question=q, top_k=8) for q in default_questions]
    Path(args.context_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.context_out).write_text(json.dumps(context_packs, ensure_ascii=False, indent=2), encoding="utf-8")

    pipeline_report = {
        "input": args.input,
        "extractor": args.extractor,
        "model": args.model if args.extractor == "ollama" else None,
        "counts": {
            "artifacts": len(snapshot.artifacts),
            "entities": len(snapshot.entities),
            "claims": len(snapshot.claims),
            "merges": len(snapshot.merges),
        },
        "validation": {
            "invalid_claims": validation_summary.invalid_claims,
            "repaired_claims": validation_summary.repaired_claims,
        },
        "warnings": extraction_warnings,
        "artifact_canonical_map": artifact_canonical_map,
        "outputs": {
            "snapshot": args.snapshot_out,
            "graph": args.graph_out,
            "context_packs": args.context_out,
        },
    }

    report_path = Path("outputs/pipeline_report.json")
    report_path.write_text(json.dumps(pipeline_report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(pipeline_report, indent=2))


if __name__ == "__main__":
    main()
