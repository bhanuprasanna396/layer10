# Layer10 Take-Home: Grounded Long-Term Memory Graph

This repository implements an end-to-end pipeline for:
1. downloading a public GitHub issues corpus,
2. extracting typed, grounded entities/claims,
3. deduplicating artifacts/entities/claims with reversible merge logs,
4. building a memory graph with temporal semantics,
5. retrieving grounded context packs for questions, and
6. visualizing entities/claims/evidence in a Streamlit app.

The design is intentionally opinionated around long-term correctness, provenance, and update safety.

## Corpus Choice
Primary corpus target: `GitHub Issues + Comments` for a public repository (e.g. `pallets/flask`, `tiangolo/fastapi`, etc.).

Why this corpus works well:
- combines structured state (`open/closed`, labels, assignees) with unstructured discussion,
- includes revisions and conflicting statements,
- exposes entity alias and dedup challenges,
- maps naturally to Layer10's chat/email + ticket fusion goal.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## End-to-End Run

### Option A: Public corpus (recommended for final submission)
```bash
export GITHUB_TOKEN=<optional_but_recommended>
python scripts/download_github_corpus.py \
  --repo pallets/flask \
  --max-issues 120 \
  --out data/raw/github_corpus.json

python scripts/run_pipeline.py \
  --input data/raw/github_corpus.json \
  --extractor heuristic
```

### Option B: Free model extraction (Ollama)
```bash
ollama pull qwen2.5:3b
python scripts/run_pipeline.py \
  --input data/raw/github_corpus.json \
  --extractor ollama \
  --model qwen2.5:3b
```

## Retrieval API (script)
```bash
python scripts/retrieve.py \
  --snapshot outputs/memory_snapshot.json \
  --question "Who owns active webhook retry work?" \
  --top-k 8
```

Output: grounded context pack with ranked claims, evidence excerpts, source URLs, and conflict summaries.

## Visualization
```bash
streamlit run layer10_memory/visualization/app.py
```

UI supports:
- filtering by claim type/status/confidence,
- claim inspection with exact evidence excerpts and source links,
- graph view for entities and relations,
- merge operation inspection (artifact/entity/claim).

## Main Outputs
- `outputs/memory_snapshot.json`: canonical entities, claims, artifacts, merge ledger
- `outputs/memory_graph.json`: graph serialization (node-link JSON)
- `outputs/context_packs.json`: example grounded retrieval outputs
- `outputs/pipeline_report.json`: run metadata + validation report

## Quality Controls Implemented
- strict extraction contract with evidence required for every claim,
- validation and repair stage (confidence bounds, orphan claim removal, evidence checks),
- idempotent deterministic IDs and canonicalization,
- multi-level dedup with reversible merge operations,
- temporal conflict handling (`current` vs `superseded` vs `conflicted`),
- auditable retrieval that only returns claims with citations.

## Project Structure
```text
scripts/
  download_github_corpus.py
  run_pipeline.py
  retrieve.py
layer10_memory/
  corpus/github.py
  extraction/{contract.py,heuristic.py,ollama.py,validate.py}
  dedup/{artifact.py,entity.py,claim.py}
  graph/{builder.py,store.py}
  retrieval/context_pack.py
  visualization/app.py
  schemas.py
  utils.py
```

## Notes
- If `ollama` is unavailable, the pipeline still runs with the deterministic extractor.
- For final internship submission, run on a real public repo corpus and include screenshots from the Streamlit UI.
