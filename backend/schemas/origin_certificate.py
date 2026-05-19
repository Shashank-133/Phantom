"""Origin Certificate — the forensic verdict per document.

Produced by services/origin_engine.py from the combined signals of:
- PDF metadata (producer string, fonts, creation date)
- Entropy profile (8-bucket Shannon entropy of raw bytes)
- ViT 768-dim CLS embedding (when available)
- ImageHash perceptual hash of page 0

Compared against the synthetic CBS reference corpus built in
backend/seed/build_cbs_corpus.py (Upgrade B, PHANTOM_MASTER_PLAN.md §14).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolCategory(str, Enum):
    CORE_BANKING_SYSTEM = "core_banking_system"
    CONSUMER_DESIGN_TOOL = "consumer_design_tool"
    OFFICE_PRODUCTIVITY = "office_productivity"
    UNKNOWN = "unknown"


# Producer string allowlists used by services/pdf_parser.py for tool classification.
# These match real strings written into the PDF /Producer or /Creator metadata fields.
CORE_BANKING_PRODUCERS = {
    "Finacle", "BankWare", "Temenos", "FinnOne", "TCS BaNCS",
    "Oracle FLEXCUBE", "FLEXCUBE", "Infosys Finacle",
}
CONSUMER_DESIGN_PRODUCERS = {
    "Canva", "Adobe Illustrator", "Photoshop", "Google Slides",
    "Keynote", "LibreOffice Draw", "Affinity Designer", "Figma",
}
OFFICE_PRODUCTIVITY_PRODUCERS = {
    "Microsoft Word", "Microsoft Excel", "Google Docs",
    "LibreOffice Writer", "Pages", "OpenOffice",
}


class PDFMetadata(BaseModel):
    """Raw extraction output from services/pdf_parser.py.

    No analysis here — just what's in the file. The origin_engine combines this
    with the entropy profile and ViT embedding to produce the certificate.
    """

    producer: str | None = None
    creator: str | None = None
    creation_date: datetime | None = None
    modification_date: datetime | None = None
    title: str | None = None
    author: str | None = None
    page_count: int = 0
    font_names: list[str] = Field(default_factory=list)
    subsetted_fonts: list[str] = Field(default_factory=list)
    file_size_bytes: int = 0
    tool_category: ToolCategory = ToolCategory.UNKNOWN

    @property
    def font_subsetting_ratio(self) -> float:
        """Fraction of fonts that are subsetted (high = CBS-like)."""
        if not self.font_names:
            return 0.0
        return len(self.subsetted_fonts) / len(self.font_names)


class EntropyProfile(BaseModel):
    """Output of services/entropy_analyzer.py.

    Real CBS PDFs typically have high entropy in middle byte sections
    (compressed image streams) and lower entropy at start/end (header/trailer).
    Consumer-tool PDFs produce flatter profiles.
    """

    buckets: list[float] = Field(..., min_length=8, max_length=8)
    mean_entropy: float
    entropy_variance: float
    profile_type: str = Field(..., pattern=r"^(cbs_like|consumer_like|unknown)$")

    def cosine_to(self, other: "EntropyProfile") -> float:
        """Cosine similarity to another profile. Used by cross_signal_engine."""
        import numpy as np

        a = np.array(self.buckets, dtype=float)
        b = np.array(other.buckets, dtype=float)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denom)


class OriginCertificate(BaseModel):
    """The forensic verdict on a single document.

    Produced once per uploaded PDF. Persisted in Postgres. Read by
    graph_builder (for template/font matching edges) and cross_signal_engine
    (to score whether a Louvain cluster is a real fraud ring).
    """

    model_config = ConfigDict(from_attributes=True)

    doc_id: UUID
    application_id: UUID

    # The headline number — 1.0 = genuine CBS doc, 0.0 = consumer-tool doc.
    cbs_match_score: float = Field(..., ge=0.0, le=1.0)

    # Best-guess origin tool name (e.g. "Canva 2.0", "Finacle 7.3", "Unknown").
    origin_tool: str
    tool_category: ToolCategory

    # Confidence of the verdict itself (independent of cbs_match_score).
    # Low when signals disagree or ViT failed; high when they all align.
    confidence: float = Field(..., ge=0.0, le=1.0)

    # MD5 of sorted font names — used to detect "same template" across applicants.
    font_subset_hash: str

    # Per-signal scores, exposed for the OriginTree UI panel.
    entropy_profile: EntropyProfile
    perceptual_hash: str  # 64-bit pHash hex, ~16 chars
    vit_embedding: list[float] | None = None  # 768-dim, None if ViT was skipped

    # Echoed metadata so the cert is self-contained for the evidence bundle.
    pdf_metadata: PDFMetadata
    creation_timestamp: datetime | None = None
