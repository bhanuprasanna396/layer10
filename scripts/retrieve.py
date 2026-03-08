#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from layer10_memory.graph.store import load_snapshot
from layer10_memory.retrieval.context_pack import build_context_pack



def main() -> None:
    parser = argparse.ArgumentParser(description="Query memory snapshot and return grounded context pack")
    parser.add_argument("--snapshot", default="outputs/memory_snapshot.json")
    parser.add_argument("--question", required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--out", default="outputs/context_pack.single.json")
    args = parser.parse_args()

    snapshot = load_snapshot(args.snapshot)
    context_pack = build_context_pack(snapshot, question=args.question, top_k=args.top_k)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(context_pack, f, ensure_ascii=False, indent=2)

    print(json.dumps(context_pack, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
