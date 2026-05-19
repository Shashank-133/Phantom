"""Build the synthetic CBS reference corpus (Upgrade B).

Generates 100 synthetic "genuine bank" PDFs with realistic Finacle/BaNCS/
FLEXCUBE/Temenos producer strings, runs them through pdf_parser +
entropy_analyzer + ViT, and aggregates the fingerprints into a single
reference object saved at models/cbs_reference.pkl.

Run ONCE before the first analysis:
    python -m backend.seed.build_cbs_corpus

After it exists, services/origin_engine.py automatically picks it up and
switches from heuristic scoring to real distance-to-centroid math.

This script is idempotent — re-running it rebuilds the reference from scratch.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
from loguru import logger

# Make `from <pkg> import` work when running as a script from project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import get_settings  # noqa: E402
from ml.vit_inference import extract_forensic_features, preload as preload_vit  # noqa: E402
from services.entropy_analyzer import analyze_entropy  # noqa: E402
from services.origin_engine import CBSReference  # noqa: E402
from services.pdf_parser import parse_pdf  # noqa: E402

from seed.cbs_pdf_factory import (  # noqa: E402
    generate_cbs_corpus_data,
    make_cbs_pdf_bytes,
)


def build(n_samples: int = 100, save_pdfs_dir: Path | None = None) -> CBSReference:
    """Generate the corpus and aggregate into a CBSReference object."""
    settings = get_settings()
    output_path = settings.models_path / "cbs_reference.pkl"
    settings.models_path.mkdir(parents=True, exist_ok=True)

    logger.info("Building CBS reference corpus | n_samples={} | out={}", n_samples, output_path)

    # Try to warm the ViT model once. If it fails (e.g. models not downloaded
    # yet), we proceed without ViT embeddings — the corpus is still useful for
    # entropy + font + producer matching.
    vit_ready = preload_vit()
    if not vit_ready:
        logger.warning(
            "ViT model not available — CBS corpus will have mean_vit_embedding=None. "
            "Run `python backend/download_models.py` first to enable the ViT signal."
        )

    samples = generate_cbs_corpus_data(n=n_samples)

    entropy_buckets: list[list[float]] = []
    vit_embeddings: list[list[float]] = []
    font_hashes: set[str] = set()
    producers: set[str] = set()

    for i, (slip, meta) in enumerate(samples, start=1):
        pdf_bytes = make_cbs_pdf_bytes(
            slip,
            producer=meta["producer"],
            creator=meta["creator"],
            creation_date=meta["creation_date"],
        )

        if save_pdfs_dir is not None:
            save_pdfs_dir.mkdir(parents=True, exist_ok=True)
            (save_pdfs_dir / f"cbs_{i:03d}.pdf").write_bytes(pdf_bytes)

        parsed = parse_pdf(pdf_bytes)
        entropy_profile = analyze_entropy(pdf_bytes)
        entropy_buckets.append(entropy_profile.buckets)

        # Font subset hash (concatenated lowercase sorted font names → md5)
        # Done inline so we don't import from origin_engine (avoids cycle).
        import hashlib

        font_hash = hashlib.md5(
            "|".join(sorted(f.lower().strip() for f in parsed.metadata.font_names)).encode()
        ).hexdigest()
        font_hashes.add(font_hash)

        if parsed.metadata.producer:
            producers.add(parsed.metadata.producer)

        if vit_ready:
            embedding = extract_forensic_features(parsed.page0_image, timeout_seconds=30.0)
            if embedding is not None:
                vit_embeddings.append(embedding)

        if i % 10 == 0:
            logger.info("  processed {}/{}", i, n_samples)

    # Aggregate
    entropy_arr = np.array(entropy_buckets, dtype=float)
    mean_entropy = entropy_arr.mean(axis=0)

    mean_vit: np.ndarray | None = None
    if vit_embeddings:
        vit_arr = np.array(vit_embeddings, dtype=float)
        mean_vit = vit_arr.mean(axis=0)
        # Re-normalize the centroid so cosine math stays in [-1, 1].
        norm = np.linalg.norm(mean_vit)
        if norm > 0:
            mean_vit = mean_vit / norm

    reference = CBSReference(
        mean_entropy_buckets=mean_entropy,
        mean_vit_embedding=mean_vit,
        expected_font_subset_hashes=font_hashes,
        producer_whitelist=producers,
        n_samples=n_samples,
    )

    with output_path.open("wb") as f:
        pickle.dump(reference, f)

    logger.info(
        "CBS reference saved | samples={} | font_hashes={} | producers={} | vit={}",
        reference.n_samples,
        len(reference.expected_font_subset_hashes),
        len(reference.producer_whitelist),
        "yes" if mean_vit is not None else "no",
    )
    logger.info("Path: {}", output_path)
    return reference


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PHANTOM CBS reference corpus")
    parser.add_argument("-n", "--n-samples", type=int, default=100,
                         help="Number of synthetic CBS PDFs to generate (default 100)")
    parser.add_argument("--save-pdfs", type=Path, default=None,
                         help="Optional dir to save generated PDFs (for debugging)")
    args = parser.parse_args()

    try:
        build(n_samples=args.n_samples, save_pdfs_dir=args.save_pdfs)
    except Exception as e:
        logger.exception("CBS corpus build failed: {}", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
