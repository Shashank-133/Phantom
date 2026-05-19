"""Community detection — pulls the Neo4j graph into NetworkX and runs Louvain.

This is the engine that surfaces "clusters of applicants who shouldn't be
related." Louvain modularity maximization is the right algorithm for this:
unsupervised, weighted, scales fine for the demo's 40 nodes (and would scale
to many thousands).

Output:
  partitions:           {application_id: community_id}
  suspicious_clusters:  list of clusters that pass our triage rule:
                          size >= 3 AND has at least one TEMPLATE_MATCH or
                          TIMING_PROXIMITY edge (i.e. something forensic
                          beyond circumstantial PII / name overlap)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

import community as community_louvain
import networkx as nx
from loguru import logger

from database.neo4j_client import Neo4jClient
from services.graph_builder import EDGE_WEIGHTS

# Cluster triage thresholds.
MIN_CLUSTER_SIZE = 3
TRIAGE_FORENSIC_EDGE_TYPES = {"TEMPLATE_MATCH", "TIMING_PROXIMITY"}


@dataclass
class SuspiciousCluster:
    community_id: int
    member_ids: list[UUID]
    edges_by_type: dict[str, int] = field(default_factory=dict)
    total_edge_weight: float = 0.0

    def as_dict(self) -> dict:
        return {
            "community_id": self.community_id,
            "member_ids": [str(m) for m in self.member_ids],
            "size": len(self.member_ids),
            "edges_by_type": self.edges_by_type,
            "total_edge_weight": round(self.total_edge_weight, 4),
        }


@dataclass
class DetectionResult:
    partitions: dict[UUID, int]
    suspicious_clusters: list[SuspiciousCluster]
    graph_node_count: int
    graph_edge_count: int

    def as_dict(self) -> dict:
        return {
            "partitions": {str(k): v for k, v in self.partitions.items()},
            "suspicious_clusters": [c.as_dict() for c in self.suspicious_clusters],
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
        }


async def _fetch_graph(neo4j: Neo4jClient) -> nx.Graph:
    """Build a NetworkX undirected weighted multigraph view from Neo4j.

    Different Neo4j edge types between the same pair get summed into one
    NetworkX edge whose weight is the max across types. We also keep the
    set of relation types on each edge for downstream triage.
    """
    g = nx.Graph()

    # Nodes
    nodes = await neo4j.run(
        "MATCH (a:Application) RETURN a.id AS id, a.applicant_name AS name, "
        "a.cbs_match_score AS cbs, a.origin_tool AS tool"
    )
    for row in nodes:
        try:
            uid = UUID(row["id"])
        except (ValueError, TypeError, AttributeError):
            continue
        g.add_node(
            uid,
            applicant_name=row.get("name"),
            cbs_match_score=row.get("cbs"),
            origin_tool=row.get("tool"),
        )

    # Edges — fetch each type separately so we know which types are present
    for rel, base_weight in EDGE_WEIGHTS.items():
        rows = await neo4j.run(
            f"MATCH (a:Application)-[r:{rel}]->(b:Application) "
            f"RETURN a.id AS a, b.id AS b, r.weight AS weight"
        )
        for row in rows:
            try:
                ua = UUID(row["a"])
                ub = UUID(row["b"])
            except (ValueError, TypeError, AttributeError):
                continue
            weight = row.get("weight") or base_weight

            if g.has_edge(ua, ub):
                existing = g[ua][ub]
                existing["weight"] = max(existing["weight"], float(weight))
                existing["rel_types"].add(rel)
            else:
                g.add_edge(ua, ub, weight=float(weight), rel_types={rel})

    logger.debug(
        "Fetched graph from Neo4j | nodes={} | edges={}",
        g.number_of_nodes(),
        g.number_of_edges(),
    )
    return g


def _run_louvain(g: nx.Graph) -> dict[UUID, int]:
    if g.number_of_edges() == 0:
        # No edges = every node is its own community.
        return {n: i for i, n in enumerate(g.nodes())}

    return community_louvain.best_partition(g, weight="weight", random_state=42)


def _triage_clusters(
    g: nx.Graph, partitions: dict[UUID, int]
) -> list[SuspiciousCluster]:
    """Group nodes by community and filter to the suspicious ones."""
    by_community: dict[int, list[UUID]] = defaultdict(list)
    for node, comm in partitions.items():
        by_community[comm].append(node)

    suspicious: list[SuspiciousCluster] = []
    for comm_id, members in by_community.items():
        if len(members) < MIN_CLUSTER_SIZE:
            continue

        member_set = set(members)
        edges_by_type: dict[str, int] = defaultdict(int)
        total_weight = 0.0
        has_forensic_edge = False

        # Count edges that live entirely inside this community.
        for u, v, data in g.edges(data=True):
            if u not in member_set or v not in member_set:
                continue
            total_weight += float(data.get("weight", 0.0))
            for rel in data.get("rel_types", set()):
                edges_by_type[rel] += 1
                if rel in TRIAGE_FORENSIC_EDGE_TYPES:
                    has_forensic_edge = True

        if not has_forensic_edge:
            # Triage rule: skip clusters that only share PII/names/etc — those
            # are circumstantial. We require at least one "this document came
            # from the same place" signal.
            continue

        # Members ordered by submission_time when available — useful for UI.
        members_sorted = sorted(
            members,
            key=lambda m: g.nodes[m].get("applicant_name") or str(m),
        )

        suspicious.append(
            SuspiciousCluster(
                community_id=comm_id,
                member_ids=members_sorted,
                edges_by_type=dict(edges_by_type),
                total_edge_weight=total_weight,
            )
        )

    # Sort: biggest, then most-edges first — the cinematic-reveal candidate is on top.
    suspicious.sort(key=lambda c: (-len(c.member_ids), -c.total_edge_weight))
    return suspicious


async def detect_communities(neo4j: Neo4jClient) -> DetectionResult:
    """End-to-end: read graph, run Louvain, surface suspicious clusters."""
    g = await _fetch_graph(neo4j)
    partitions = _run_louvain(g)
    suspicious = _triage_clusters(g, partitions)

    logger.info(
        "Louvain done | communities={} | suspicious={}",
        len(set(partitions.values())),
        len(suspicious),
    )
    return DetectionResult(
        partitions=partitions,
        suspicious_clusters=suspicious,
        graph_node_count=g.number_of_nodes(),
        graph_edge_count=g.number_of_edges(),
    )
