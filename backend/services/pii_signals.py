"""PII overlap scoring — Upgrade A signal #1.

For every pair of applications, compute a weighted PII overlap score in [0, 1]:

    bank account first-6 digits match  → +0.30
    same IFSC                          → +0.20
    same phone prefix (first 6 digits) → +0.30
    same email domain (non-generic)    → +0.40
    PAN first 4 chars match            → +0.20

Pairs with score > SHARED_PII_THRESHOLD get a SHARED_PII edge in Neo4j.

Catches rings that use different document templates but share phone-number
prefixes, account-number ranges, or domain patterns — common when fraudsters
recycle a small pool of throwaway identities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Weighted-sum cutoff for declaring a SHARED_PII edge. 0.40 means "two
# strong signals (e.g. same bank prefix + same IFSC)" is enough, while a
# single shared phone prefix alone (0.30) is not. Calibrated so genuine
# applicants who happen to share one identifier don't get flagged, but ring
# members who share 2+ identifiers do.
SHARED_PII_THRESHOLD = 0.40

# Generic email domains — sharing one of these is not informative.
_GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "yahoo.in", "outlook.com",
    "hotmail.com", "rediffmail.com", "live.com", "icloud.com", "protonmail.com",
}

_PHONE_DIGITS_RE = re.compile(r"\d")


@dataclass(frozen=True)
class PIIFingerprint:
    """Normalized PII for one applicant — pre-computed once, reused for all pair comparisons."""

    bank_account_prefix6: str | None
    ifsc: str | None
    phone_prefix6: str | None     # first 6 digits AFTER stripping country code
    email_domain: str | None     # lowercased; None if generic or missing
    pan_prefix4: str | None


def _normalize_phone(phone: str | None) -> str | None:
    """Strip non-digits; if starts with country code (91, 1, 44...), drop it.

    Heuristic: take the trailing 10 digits (Indian mobile length) and use
    those. Returns the first 6 of those 10 as the prefix.
    """
    if not phone:
        return None
    digits = "".join(_PHONE_DIGITS_RE.findall(phone))
    if not digits:
        return None
    # Drop country-code lead if total length > 10
    if len(digits) > 10:
        digits = digits[-10:]
    if len(digits) < 6:
        return None
    return digits[:6]


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    if not domain or domain in _GENERIC_EMAIL_DOMAINS:
        return None
    return domain


def fingerprint(applicant: dict) -> PIIFingerprint:
    """Pre-compute the fingerprint once per applicant."""
    bank = (applicant.get("bank_account") or "").strip()
    bank_prefix = bank[:6] if len(bank) >= 6 else None

    ifsc = (applicant.get("ifsc") or "").strip().upper() or None
    pan = (applicant.get("pan") or "").strip().upper()
    pan_prefix = pan[:4] if len(pan) >= 4 else None

    return PIIFingerprint(
        bank_account_prefix6=bank_prefix,
        ifsc=ifsc,
        phone_prefix6=_normalize_phone(applicant.get("phone")),
        email_domain=_email_domain(applicant.get("email")),
        pan_prefix4=pan_prefix,
    )


def overlap_score(a: PIIFingerprint, b: PIIFingerprint) -> float:
    score = 0.0

    if a.bank_account_prefix6 and a.bank_account_prefix6 == b.bank_account_prefix6:
        score += 0.30
    if a.ifsc and a.ifsc == b.ifsc:
        score += 0.20
    if a.phone_prefix6 and a.phone_prefix6 == b.phone_prefix6:
        score += 0.30
    if a.email_domain and a.email_domain == b.email_domain:
        score += 0.40
    if a.pan_prefix4 and a.pan_prefix4 == b.pan_prefix4:
        score += 0.20

    return min(score, 1.0)


def is_shared_pii(a: PIIFingerprint, b: PIIFingerprint) -> bool:
    return overlap_score(a, b) > SHARED_PII_THRESHOLD


def cluster_pii_overlap_fraction(
    fingerprints: list[PIIFingerprint],
) -> float:
    """Fraction of unordered pairs in the cluster that exceed the PII threshold.

    Used by cross_signal_engine's behavioral_score component. Range [0, 1].
    """
    n = len(fingerprints)
    if n < 2:
        return 0.0

    matches = 0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            pairs += 1
            if is_shared_pii(fingerprints[i], fingerprints[j]):
                matches += 1

    return matches / pairs if pairs else 0.0
