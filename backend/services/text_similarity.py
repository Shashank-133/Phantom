"""Text similarity scoring — Upgrade A signal #2.

Embeds the concatenated free-text fields of each application
(purpose_of_loan + employer_description + address_line_2) with the
all-MiniLM-L6-v2 sentence-transformer, then computes pairwise cosine
similarity. Pairs above TEXT_MATCH_THRESHOLD get a TEXT_MATCH edge.

This is where the all-MiniLM-L6-v2 model earns its keep. The 11 fraud-ring
applicants all list "small business expansion" verbatim — their embeddings
cluster tightly while genuine applicants who wrote varied purposes scatter.

Pre-computed per-applicant embeddings are cached in the returned dict; the
caller (graph_builder) feeds them to many pairwise comparisons.
"""
from __future__ import annotations

from uuid import UUID

import numpy as np
from loguru import logger

from ml.embedding_model import EMBEDDING_DIM, cosine_similarity, embed_batch

# Cosine-similarity threshold for declaring a TEXT_MATCH edge between two
# applicants' free-text fields. 0.70 catches "shares a strong verbatim chunk"
# (e.g. same purpose-of-loan + similar employer description) without flagging
# generic banking language. Random unrelated business descriptions sit < 0.5.
TEXT_MATCH_THRESHOLD = 0.70


def _compose_text(applicant: dict) -> str:
    """Concatenate the free-text fields into a single string for embedding."""
    parts = [
        applicant.get("purpose_of_loan") or "",
        applicant.get("employer_description") or "",
        applicant.get("address_line_2") or "",
    ]
    return " | ".join(p.strip() for p in parts if p.strip())


def compute_embeddings(applicants: list[dict]) -> dict[UUID | str, np.ndarray] | None:
    """Return a dict mapping application_id → 384-dim embedding.

    Returns None if the embedding model is unavailable — callers should then
    skip text-match edge creation.
    """
    if not applicants:
        return {}

    ids = [a.get("id") or a.get("application_id") for a in applicants]
    texts = [_compose_text(a) for a in applicants]

    vecs = embed_batch(texts)
    if vecs is None:
        logger.warning("Sentence-transformer unavailable — TEXT_MATCH skipped for this batch")
        return None

    return {ids[i]: vecs[i] for i in range(len(ids))}


def pair_similarity(
    embeddings: dict, app_id_a: UUID | str, app_id_b: UUID | str
) -> float:
    a = embeddings.get(app_id_a)
    b = embeddings.get(app_id_b)
    if a is None or b is None:
        return 0.0
    if a.shape != (EMBEDDING_DIM,) or b.shape != (EMBEDDING_DIM,):
        return 0.0
    if not np.any(a) or not np.any(b):
        return 0.0
    return cosine_similarity(a, b)


def is_text_match(embeddings: dict, app_id_a: UUID | str, app_id_b: UUID | str) -> bool:
    return pair_similarity(embeddings, app_id_a, app_id_b) > TEXT_MATCH_THRESHOLD


def cluster_text_similarity_fraction(
    embeddings: dict, app_ids: list[UUID | str]
) -> float:
    """Fraction of unordered pairs in the cluster that exceed the threshold."""
    n = len(app_ids)
    if n < 2:
        return 0.0

    matches = 0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            pairs += 1
            if is_text_match(embeddings, app_ids[i], app_ids[j]):
                matches += 1

    return matches / pairs if pairs else 0.0
