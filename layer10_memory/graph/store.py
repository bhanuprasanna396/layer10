from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from layer10_memory.schemas import MemoryGraphSnapshot



def save_snapshot(snapshot: MemoryGraphSnapshot, path: str | Path) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")



def load_snapshot(path: str | Path) -> MemoryGraphSnapshot:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return MemoryGraphSnapshot.model_validate(payload)



def save_graph_json(graph: nx.MultiDiGraph, path: str | Path) -> None:
    data = json_graph.node_link_data(graph)
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")



def load_graph_json(path: str | Path) -> nx.MultiDiGraph:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return json_graph.node_link_graph(payload, directed=True, multigraph=True)
