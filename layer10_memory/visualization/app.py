from __future__ import annotations

import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from layer10_memory.graph.store import load_snapshot


@st.cache_data(show_spinner=False)
def _load_snapshot(path: str):
    return load_snapshot(path)


def main() -> None:
    st.set_page_config(page_title="Layer10 Memory Graph Explorer", layout="wide")
    st.title("Layer10 Memory Graph Explorer")

    default_path = "outputs/memory_snapshot.json"
    snapshot_path = st.sidebar.text_input("Snapshot path", value=default_path)

    if not Path(snapshot_path).exists():
        st.warning(f"Snapshot not found at {snapshot_path}. Run scripts/run_pipeline.py first.")
        return

    snapshot = _load_snapshot(snapshot_path)
    entity_by_id = {entity.entity_id: entity for entity in snapshot.entities}

    claim_types = sorted({claim.claim_type for claim in snapshot.claims})
    statuses = sorted({claim.status for claim in snapshot.claims})

    selected_types = st.sidebar.multiselect("Claim types", claim_types, default=claim_types)
    selected_status = st.sidebar.multiselect("Status", statuses, default=statuses)
    min_conf = st.sidebar.slider("Min confidence", 0.0, 1.0, 0.55, 0.01)

    filtered_claims = [
        claim
        for claim in snapshot.claims
        if claim.claim_type in selected_types and claim.status in selected_status and claim.confidence >= min_conf
    ]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artifacts", len(snapshot.artifacts))
    c2.metric("Entities", len(snapshot.entities))
    c3.metric("Claims (filtered)", len(filtered_claims))
    c4.metric("Merges", len(snapshot.merges))

    claim_rows = []
    for claim in filtered_claims:
        subject = entity_by_id.get(claim.subject_entity_id)
        object_entity = entity_by_id.get(claim.object_entity_id) if claim.object_entity_id else None
        claim_rows.append(
            {
                "claim_id": claim.claim_id,
                "claim_type": claim.claim_type,
                "subject": subject.canonical_name if subject else claim.subject_entity_id,
                "object": object_entity.canonical_name if object_entity else (claim.value or ""),
                "status": claim.status,
                "confidence": round(claim.confidence, 3),
                "event_time": claim.event_time.isoformat() if claim.event_time else "",
            }
        )

    claims_df = pd.DataFrame(claim_rows)
    st.subheader("Claims")
    st.dataframe(claims_df, use_container_width=True)

    if claims_df.empty:
        st.info("No claims match the selected filters.")
        return

    selected_claim_id = st.selectbox("Inspect claim", claims_df["claim_id"].tolist())
    selected_claim = next(claim for claim in filtered_claims if claim.claim_id == selected_claim_id)

    st.subheader("Evidence")
    for idx, evidence in enumerate(selected_claim.evidence, start=1):
        st.markdown(f"**Evidence {idx}**")
        st.code(evidence.excerpt)
        st.markdown(
            f"Source: [{evidence.source_url}]({evidence.source_url}) | Artifact: `{evidence.artifact_id}` | "
            f"Offsets: `{evidence.char_start}`-`{evidence.char_end}`"
        )

    st.subheader("Graph View")
    fig = _build_graph_figure(filtered_claims, entity_by_id)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Merge Operations")
    merge_rows = [
        {
            "operation_id": merge.operation_id,
            "merge_type": merge.merge_type,
            "winner_id": merge.winner_id,
            "loser_ids": ", ".join(merge.loser_ids),
            "reason": merge.reason,
            "score": merge.score,
            "reversible": merge.reversible,
        }
        for merge in snapshot.merges
    ]
    st.dataframe(pd.DataFrame(merge_rows), use_container_width=True)



def _build_graph_figure(filtered_claims, entity_by_id):
    graph = nx.DiGraph()

    for claim in filtered_claims[:220]:
        subject = entity_by_id.get(claim.subject_entity_id)
        object_entity = entity_by_id.get(claim.object_entity_id) if claim.object_entity_id else None
        subject_label = subject.canonical_name if subject else claim.subject_entity_id
        object_label = object_entity.canonical_name if object_entity else (claim.value or "(value)")

        graph.add_node(subject_label, kind="entity")
        graph.add_node(object_label, kind="entity")
        graph.add_edge(subject_label, object_label, label=claim.claim_type, confidence=claim.confidence)

    if graph.number_of_nodes() == 0:
        return go.Figure()

    pos = nx.spring_layout(graph, seed=42, k=1.2 / max(1, len(graph.nodes())))

    edge_x = []
    edge_y = []
    for src, dst in graph.edges():
        x0, y0 = pos[src]
        x1, y1 = pos[dst]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        mode="lines",
    )

    node_x = []
    node_y = []
    node_text = []
    for node in graph.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        hoverinfo="text",
        marker=dict(size=14, color="#2E86AB", line=dict(width=1, color="#0B1F33")),
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=650,
    )
    return fig


if __name__ == "__main__":
    main()
