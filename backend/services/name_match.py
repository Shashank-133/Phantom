"""Fuzzy name matching — Upgrade A signal #3.

Catches near-duplicate applicant names that a ring might use to register
multiple identities:

    "Rahul Sharma"   /  "Rahul Sharrma"   (Levenshtein 1)
    "Sandeep Patil"  /  "Sandip Patil"    (Levenshtein 1)
    "Anil Kumar"     /  "A Kumar"         (rapidfuzz partial ratio)

Decision rule (a NAME_SIMILARITY edge fires when ANY of these are true):
  1. Normalized Levenshtein distance ≤ 2
  2. Token-sort fuzzy ratio ≥ 90 (catches reordered tokens / initials)
  3. Sub-name overlap (e.g. shared surname AND shared first-name initial)

Names are normalized first — lowercased, whitespace-collapsed, honorifics
stripped — so trivial cosmetic differences don't dominate the comparison.
"""
from __future__ import annotations

import re

from rapidfuzz.distance import Levenshtein
from rapidfuzz.fuzz import token_sort_ratio

NAME_MATCH_RATIO_THRESHOLD = 90
NAME_MATCH_LEVENSHTEIN_MAX = 2

_HONORIFICS = {
    "mr", "mrs", "ms", "miss", "dr", "shri", "smt", "kumari", "sri",
    "prof", "professor", "er", "engineer", "advocate", "adv",
}
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    s = _WHITESPACE_RE.sub(" ", s)
    tokens = [t for t in s.split() if t.rstrip(".") not in _HONORIFICS]
    return " ".join(tokens)


def _surname_first_initial(name: str) -> tuple[str, str]:
    """Return (last_token, first_token_first_letter) of a normalized name."""
    tokens = name.split()
    if not tokens:
        return ("", "")
    return (tokens[-1], tokens[0][0] if tokens[0] else "")


def is_name_similar(name_a: str | None, name_b: str | None) -> bool:
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    if not a or not b:
        return False
    if a == b:
        return True

    # 1. Tight Levenshtein on the whole string (catches single-letter typos)
    if Levenshtein.distance(a, b) <= NAME_MATCH_LEVENSHTEIN_MAX:
        return True

    # 2. Token-sort fuzzy ratio (catches reorderings, partial names)
    if token_sort_ratio(a, b) >= NAME_MATCH_RATIO_THRESHOLD:
        return True

    # 3. Shared surname + shared first-initial (covers "R Sharma" / "Rahul Sharma")
    sur_a, init_a = _surname_first_initial(a)
    sur_b, init_b = _surname_first_initial(b)
    if (
        sur_a and sur_a == sur_b
        and init_a and init_a == init_b
        and len(sur_a) >= 4   # avoid colliding on single-letter surnames
    ):
        return True

    return False


def cluster_name_similarity_fraction(names: list[str | None]) -> float:
    """Fraction of unordered pairs in the cluster judged 'similar'."""
    n = len(names)
    if n < 2:
        return 0.0

    matches = 0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            pairs += 1
            if is_name_similar(names[i], names[j]):
                matches += 1

    return matches / pairs if pairs else 0.0
