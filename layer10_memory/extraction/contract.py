from __future__ import annotations

from dataclasses import dataclass, field

from layer10_memory.schemas import Artifact, Claim, Entity


@dataclass
class ExtractionResult:
    artifact: Artifact
    entities: list[Entity] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BaseExtractor:
    name = "base"
    version = "0"

    def extract(self, artifact: Artifact) -> ExtractionResult:  # pragma: no cover - interface
        raise NotImplementedError
