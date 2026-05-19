"""Pre-download all HuggingFace models PHANTOM uses, into ./models/.

Run ONCE before `docker compose up`. Downloads ~450 MB total:
  - google/vit-base-patch16-224  (~350 MB)
  - sentence-transformers/all-MiniLM-L6-v2  (~90 MB)

After this completes, Docker containers find the models locally via the
TRANSFORMERS_CACHE and SENTENCE_TRANSFORMERS_HOME env vars — zero internet
needed during demo.

Usage:
    cd backend
    python download_models.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Force the cache to the project-level ./models dir before importing HF libs.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)

os.environ["TRANSFORMERS_CACHE"] = str(MODELS_DIR)
os.environ["HF_HOME"] = str(MODELS_DIR)
os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(MODELS_DIR)


def download_vit() -> None:
    print("[1/2] Downloading google/vit-base-patch16-224 ...")
    from transformers import ViTImageProcessor, ViTModel

    ViTImageProcessor.from_pretrained(
        "google/vit-base-patch16-224", cache_dir=str(MODELS_DIR)
    )
    ViTModel.from_pretrained("google/vit-base-patch16-224", cache_dir=str(MODELS_DIR))
    print("      OK")


def download_sentence_transformer() -> None:
    print("[2/2] Downloading sentence-transformers/all-MiniLM-L6-v2 ...")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("all-MiniLM-L6-v2", cache_folder=str(MODELS_DIR))
    print("      OK")


def main() -> int:
    print(f"PHANTOM model downloader")
    print(f"Target directory: {MODELS_DIR}")
    print()
    try:
        download_vit()
        download_sentence_transformer()
    except Exception as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        return 1

    total_bytes = sum(p.stat().st_size for p in MODELS_DIR.rglob("*") if p.is_file())
    total_mb = total_bytes / (1024 * 1024)
    print(f"\nDone. {total_mb:.1f} MB on disk at {MODELS_DIR}")
    print("You can now run `docker compose up`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
