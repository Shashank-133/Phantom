"""Ed25519 evidence signer.

Why Ed25519 instead of "SHA-256 the JSON":
  - SHA-256 is a hash, not a signature. Anyone can recompute it after
    tampering with the evidence. A real signature requires asymmetric
    crypto with a private key that only the signer possesses.
  - Ed25519 is fast, has 64-byte signatures, 32-byte public keys, and is
    the modern default for new systems. EdDSA per RFC 8032.

What this module provides:
  - PhantomSigner.sign(bundle_dict) → (canonical_json, signature_b64, key_id)
  - PhantomSigner.verify(canonical_json, signature_b64) → bool
  - A singleton accessor get_signer() that handles key persistence

Key persistence:
  - Private key: <PHANTOM_KEY_DIR>/phantom_ed25519_private.pem  (PEM, unencrypted)
  - Public key:  <PHANTOM_KEY_DIR>/phantom_ed25519_public.pem
  - Key fingerprint (the signing_key_id surfaced in reports): first 16 hex
    chars of SHA-256(public_key_raw_bytes)

If keys are missing, they are auto-generated on first use. The key directory
is created if needed. Both files survive container restarts because
docker-compose mounts ./keys as a volume.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from loguru import logger

from config import get_settings


_PRIVATE_KEY_FILE = "phantom_ed25519_private.pem"
_PUBLIC_KEY_FILE = "phantom_ed25519_public.pem"


def canonical_json(obj: dict) -> bytes:
    """Canonical JSON encoding — sorted keys, no whitespace, UTF-8.

    Two parties producing canonical JSON of the same dict will always get the
    same bytes. Required for signing to be reproducible.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


def _json_default(value):
    """Handle datetime, UUID, etc. in nested dicts."""
    from datetime import datetime
    from uuid import UUID

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "value"):  # enums
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


@dataclass
class SignedEvidence:
    canonical_bytes: bytes
    sha256_hex: str
    signature_b64: str
    signing_key_id: str


class PhantomSigner:
    def __init__(self, key_dir: Path) -> None:
        self._key_dir = key_dir
        self._key_dir.mkdir(parents=True, exist_ok=True)
        self._private_key: Ed25519PrivateKey
        self._public_key: Ed25519PublicKey
        self._key_id: str
        self._load_or_generate()

    @property
    def key_id(self) -> str:
        """Short fingerprint surfaced in PHANTOM reports."""
        return self._key_id

    @property
    def public_key_pem(self) -> str:
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

    def sign(self, evidence_bundle: dict) -> SignedEvidence:
        canon = canonical_json(evidence_bundle)
        sig = self._private_key.sign(canon)
        return SignedEvidence(
            canonical_bytes=canon,
            sha256_hex=hashlib.sha256(canon).hexdigest(),
            signature_b64=base64.b64encode(sig).decode("ascii"),
            signing_key_id=self._key_id,
        )

    def verify(self, canonical_bytes: bytes, signature_b64: str) -> bool:
        try:
            sig = base64.b64decode(signature_b64)
            self._public_key.verify(sig, canonical_bytes)
            return True
        except Exception as e:
            logger.warning("Signature verification failed: {}", e)
            return False

    # ---- internal -----------------------------------------------------------

    def _load_or_generate(self) -> None:
        priv_path = self._key_dir / _PRIVATE_KEY_FILE
        pub_path = self._key_dir / _PUBLIC_KEY_FILE

        if priv_path.exists() and pub_path.exists():
            self._load(priv_path, pub_path)
            logger.info("Loaded existing Ed25519 keypair | key_id={}", self._key_id)
            return

        # Generate fresh
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._write(priv_path, pub_path)
        self._key_id = self._compute_key_id()
        logger.info("Generated new Ed25519 keypair | key_id={}", self._key_id)

    def _load(self, priv_path: Path, pub_path: Path) -> None:
        priv_bytes = priv_path.read_bytes()
        loaded_priv = serialization.load_pem_private_key(priv_bytes, password=None)
        if not isinstance(loaded_priv, Ed25519PrivateKey):
            raise ValueError("Private key file is not Ed25519")
        self._private_key = loaded_priv

        pub_bytes = pub_path.read_bytes()
        loaded_pub = serialization.load_pem_public_key(pub_bytes)
        if not isinstance(loaded_pub, Ed25519PublicKey):
            raise ValueError("Public key file is not Ed25519")
        self._public_key = loaded_pub

        self._key_id = self._compute_key_id()

    def _write(self, priv_path: Path, pub_path: Path) -> None:
        priv_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        priv_path.write_bytes(priv_pem)
        pub_path.write_bytes(pub_pem)
        # Restrict perms where the OS supports it. No-op on Windows.
        try:
            priv_path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass

    def _compute_key_id(self) -> str:
        raw = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(raw).hexdigest()[:16]


_signer: PhantomSigner | None = None
_signer_lock = threading.Lock()


def get_signer() -> PhantomSigner:
    global _signer
    if _signer is not None:
        return _signer
    with _signer_lock:
        if _signer is None:
            settings = get_settings()
            _signer = PhantomSigner(settings.key_dir_path)
    return _signer
