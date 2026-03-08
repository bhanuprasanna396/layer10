from __future__ import annotations

import json
from typing import Any

import requests

from layer10_memory.config import EXTRACTION_VERSION
from layer10_memory.extraction.contract import BaseExtractor, ExtractionResult
from layer10_memory.extraction.heuristic import HeuristicExtractor
from layer10_memory.schemas import Artifact, Claim, Entity, SourcePointer
from layer10_memory.utils import normalize_text, safe_excerpt, stable_id


class OllamaExtractor(BaseExtractor):
    name = "ollama"
    version = "1.0.0"

    def __init__(
        self,
        model: str = "qwen2.5:3b",
        endpoint: str = "http://localhost:11434/api/generate",
        timeout_seconds: int = 45,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.fallback = HeuristicExtractor()

    def extract(self, artifact: Artifact) -> ExtractionResult:
        prompt = self._build_prompt(artifact)
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }

        try:
            response = requests.post(self.endpoint, json=body, timeout=self.timeout_seconds)
            response.raise_for_status()
            raw = response.json().get("response", "{}")
            payload = json.loads(raw)
            entities, claims = self._parse_payload(artifact, payload)
            if not claims:
                raise ValueError("No claims returned from model")
            return ExtractionResult(artifact=artifact, entities=entities, claims=claims)
        except Exception as exc:  # noqa: BLE001
            result = self.fallback.extract(artifact)
            result.warnings.append(f"Ollama extraction failed, fallback used: {exc}")
            return result

    def _build_prompt(self, artifact: Artifact) -> str:
        text = artifact.text[:6000]
        return (
            "Extract grounded entities and claims from the artifact. "
            "Return strict JSON with keys entities and claims. "
            "Entity schema: {entity_type, canonical_name, aliases}. "
            "Claim schema: {claim_type, subject_entity, object_entity, value, confidence, evidence_excerpt}. "
            "Only include claims supported by direct text evidence.\n"
            f"artifact_type={artifact.artifact_type}\n"
            f"source_url={artifact.source_url}\n"
            f"text:\n{text}\n"
        )

    def _parse_payload(self, artifact: Artifact, payload: dict[str, Any]) -> tuple[list[Entity], list[Claim]]:
        entity_map: dict[str, Entity] = {}

        for raw_entity in payload.get("entities", []):
            etype = raw_entity.get("entity_type", "component")
            if etype not in {
                "person",
                "team",
                "repository",
                "issue",
                "pull_request",
                "component",
                "label",
            }:
                continue
            canonical = normalize_text(raw_entity.get("canonical_name", ""))
            if not canonical:
                continue

            entity = Entity(
                entity_id=stable_id("ent", etype, canonical),
                entity_type=etype,
                canonical_name=canonical,
                aliases=sorted(set(raw_entity.get("aliases", []))),
                confidence=float(raw_entity.get("confidence", 0.7)),
            )
            entity_map[entity.entity_id] = entity

        claims: list[Claim] = []
        for raw_claim in payload.get("claims", []):
            claim_type = raw_claim.get("claim_type")
            if claim_type not in {
                "issue_state",
                "assigned_to",
                "mentions_component",
                "mentions_label",
                "blocks",
                "decision",
                "action_item",
                "ownership_change",
            }:
                continue

            subject_name = normalize_text(raw_claim.get("subject_entity", ""))
            if not subject_name:
                continue
            subject_id = self._ensure_entity(subject_name, entity_map)

            object_id = None
            object_name = normalize_text(raw_claim.get("object_entity", ""))
            if object_name:
                object_id = self._ensure_entity(object_name, entity_map)

            excerpt = str(raw_claim.get("evidence_excerpt", "")).strip()
            if not excerpt:
                continue

            start = artifact.text.lower().find(excerpt.lower())
            end = start + len(excerpt) if start >= 0 else None
            if start < 0:
                start = None
                end = None

            evidence = SourcePointer(
                source_id=stable_id("src", artifact.artifact_id, excerpt[:64], str(start), str(end)),
                artifact_id=artifact.artifact_id,
                source_url=artifact.source_url,
                excerpt=safe_excerpt(artifact.text, start, end),
                char_start=start,
                char_end=end,
                observed_at=artifact.updated_at or artifact.created_at,
            )

            claims.append(
                Claim(
                    claim_id=stable_id(
                        "clm",
                        artifact.artifact_id,
                        claim_type,
                        subject_id,
                        object_id or "",
                        str(raw_claim.get("value", ""))[:120],
                    ),
                    claim_type=claim_type,
                    subject_entity_id=subject_id,
                    object_entity_id=object_id,
                    value=raw_claim.get("value"),
                    confidence=max(0.0, min(float(raw_claim.get("confidence", 0.65)), 1.0)),
                    event_time=artifact.created_at,
                    valid_from=artifact.created_at,
                    evidence=[evidence],
                    extraction_version=EXTRACTION_VERSION,
                )
            )

        return list(entity_map.values()), claims

    @staticmethod
    def _ensure_entity(name: str, entity_map: dict[str, Entity]) -> str:
        entity_id = stable_id("ent", "component", name)
        if entity_id not in entity_map:
            entity_map[entity_id] = Entity(
                entity_id=entity_id,
                entity_type="component",
                canonical_name=name,
                confidence=0.6,
            )
        return entity_id
