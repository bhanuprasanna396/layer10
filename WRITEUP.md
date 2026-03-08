# Write-Up: Grounded Long-Term Memory via Structured Extraction, Dedup, and Graph Retrieval

## 1. Corpus and Reproducibility
Chosen corpus: public GitHub Issues + Comments for one repository (`owner/repo`).

Reproducible download command:
```bash
python scripts/download_github_corpus.py --repo pallets/flask --max-issues 120 --out data/raw/github_corpus.json
```

Download metadata is persisted in the corpus file:
- `repository`, `downloaded_at`, `source`, `max_issues`, `include_prs`, `include_timeline`.

This gives both structured artifacts (state, assignees, labels) and unstructured artifacts (bodies, comments).

## 2. Ontology and Extraction Contract

### Core entity types
- `person`, `team`, `repository`, `issue`, `pull_request`, `component`, `label`

### Core claim types
- `issue_state`
- `assigned_to`
- `mentions_component`
- `mentions_label`
- `blocks`
- `decision`
- `action_item`
- `ownership_change`

### Evidence grounding requirement
Every claim must include at least one `SourcePointer`:
- `artifact_id`
- `source_url`
- `excerpt`
- optional `char_start`, `char_end`
- `observed_at`

Claims without evidence are dropped in validation.

## 3. Extraction Pipeline

### Extractors
- `HeuristicExtractor` (deterministic, offline-safe)
- `OllamaExtractor` (`qwen2.5:3b` default) with contract-constrained JSON output

Both emit the same typed schema and evidence pointers.

### Validation and repair
`validate_and_repair` enforces:
- subject/object entity existence,
- non-empty evidence,
- confidence bounds in `[0,1]`,
- minimum confidence gate,
- evidence dedup.

### Versioning
`Claim.extraction_version` stores extractor+schema version. This supports:
- backfills when ontology changes,
- side-by-side evaluation of versions,
- rollback to previous extraction outputs.

## 4. Deduplication and Canonicalization

### Artifact dedup
- exact: normalized text hash
- near-duplicate: fuzzy text match within same issue thread
- output: canonical artifact set + reversible merge operations

### Entity canonicalization
- exact canonical merge (`entity_type + normalized_name`)
- alias fuzzy merge for people/teams (e.g., `@alex` vs `alex`)
- output: canonical entity map + merge ledger

### Claim dedup
- semantic key: `(claim_type, subject, object/value, polarity)`
- merges evidence sets and preserves highest confidence

### Conflicts and revisions
Temporal claim families (`issue_state`, `assigned_to`, `ownership_change`) are resolved into:
- `current`
- `superseded`
- `conflicted`

This preserves historical truth while exposing present uncertainty.

### Reversibility
All merges are logged as `MergeOperation` with:
- `winner_id`, `loser_ids`, `reason`, `score`, `timestamp`, `reversible`

This provides auditability and supports unmerge workflows.

## 5. Memory Graph Design
Graph contains nodes for:
- entities
- artifacts
- claims
- merge operations

Edges encode:
- subject/object claim structure
- claim-to-artifact evidence links
- merge winner/loser relations

Time semantics:
- `event_time`, `valid_from`, `valid_to`
- explicit status for current vs historical claims

Incremental update semantics:
- deterministic IDs make ingestion idempotent,
- reprocessing with new extractor/schema naturally supersedes old claims,
- deletion/redaction strategy: mark claims as invalid and remove evidence excerpts while keeping audit metadata.

## 6. Retrieval and Grounding
`build_context_pack(question)`:
- maps questions to candidate claims using BM25 lexical retrieval,
- adds entity match + confidence boosts,
- enforces claim diversity to avoid context explosion,
- returns evidence-rich context pack with citations.

Ambiguity policy:
- include conflicting variants,
- mark conflicts explicitly,
- preserve citations for both sides.

## 7. Visualization Layer
Streamlit app:
- claim filters by type/status/confidence,
- graph view of entities/relations,
- evidence panel with exact excerpts and source links,
- merge table for alias/dedup audit.

This is optimized for trust: any node/claim should be explainable via click-through provenance.

## 8. Layer10 Adaptation Plan

### Unstructured + structured fusion
- chat/email messages become artifacts linked to tickets/docs/components via shared entities and thread IDs,
- ticket systems provide authoritative state transitions while chat adds rationale/decision context.

### Durable memory vs ephemeral context
- durable: validated claims with repeated evidence and stable entities,
- ephemeral: low-confidence single-message signals with decay policies.

### Grounding and safety
- require source-level provenance for all durable claims,
- preserve tombstones for deleted/redacted sources,
- block retrieval when evidence is no longer accessible.

### Permissions
- attach ACL metadata to artifact nodes,
- retrieval only ranks claims whose supporting evidence is accessible to the caller,
- mixed-ACL evidence requires filtering or redaction at response time.

### Operational reality
- cost control via staged extraction (rules first, model only on uncertain artifacts),
- incremental ingest by source cursor (Slack channel timestamp, Jira webhook, email UID),
- regression suite over golden queries and merge decisions,
- observability for drift: conflict rate, orphan claims, merge reversals, grounding failures.

## 9. Evaluation Coverage Mapping
- Extraction system quality: schema + validation + versioning implemented.
- Grounding: every claim has evidence pointer and source URL.
- Deduplication: artifact, entity, and claim-level dedup with merge logs.
- Long-term correctness: temporal statuses and revision semantics implemented.
- Usability: retrieval outputs and Streamlit graph explorer are auditable.
- Clarity/reproducibility: scripted download/build/query flow with deterministic outputs.
