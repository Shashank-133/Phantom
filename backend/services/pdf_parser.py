"""PDF parser — extract every signal we'll need without doing any judging yet.

Pure function. Takes raw bytes, returns a PDFMetadata + page-0 PIL image +
the same raw bytes (handed forward to entropy_analyzer to avoid re-reading).

Judging — "is this Canva?" — lives in services/origin_engine.py. Here we
only collect facts.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime

import fitz  # PyMuPDF
from loguru import logger
from PIL import Image

from schemas.origin_certificate import (
    CONSUMER_DESIGN_PRODUCERS,
    CORE_BANKING_PRODUCERS,
    OFFICE_PRODUCTIVITY_PRODUCERS,
    PDFMetadata,
    ToolCategory,
)


# Subsetted fonts in PDFs are prefixed with 6 uppercase letters then a +, e.g.
# "ABCDEF+Helvetica". CBS-grade PDFs almost always subset; Canva often doesn't.
_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")

# PyMuPDF returns dates in the PDF spec format "D:YYYYMMDDHHmmSS+HH'mm'".
_PDF_DATE_RE = re.compile(
    r"D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})"
)


@dataclass
class ParsedPDF:
    """Output of parse_pdf — what every downstream service consumes."""

    metadata: PDFMetadata
    page0_image: Image.Image
    raw_bytes: bytes


def _parse_pdf_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    m = _PDF_DATE_RE.match(raw)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def _classify_tool(producer: str | None, creator: str | None) -> tuple[ToolCategory, str]:
    """Map a producer/creator string to a tool category + display name.

    The display name is "best guess of the actual tool" — e.g. "Canva 2.0",
    "Finacle 7.3", or "Unknown".
    """
    haystacks = [s for s in (producer, creator) if s]
    combined = " | ".join(haystacks)

    for prod in CORE_BANKING_PRODUCERS:
        if any(prod.lower() in h.lower() for h in haystacks):
            return ToolCategory.CORE_BANKING_SYSTEM, combined or prod

    for prod in CONSUMER_DESIGN_PRODUCERS:
        if any(prod.lower() in h.lower() for h in haystacks):
            return ToolCategory.CONSUMER_DESIGN_TOOL, combined or prod

    for prod in OFFICE_PRODUCTIVITY_PRODUCERS:
        if any(prod.lower() in h.lower() for h in haystacks):
            return ToolCategory.OFFICE_PRODUCTIVITY, combined or prod

    return ToolCategory.UNKNOWN, combined or "Unknown"


def _extract_fonts(doc: fitz.Document) -> tuple[list[str], list[str]]:
    """Return (all_font_names, subsetted_font_names). Deduped, sorted."""
    all_fonts: set[str] = set()
    subsetted: set[str] = set()

    for page in doc:
        # get_fonts returns list of tuples: (xref, ext, type, basefont, name, encoding)
        for font in page.get_fonts(full=True):
            basefont = font[3] if len(font) > 3 else ""
            if not basefont:
                continue
            all_fonts.add(basefont)
            if _SUBSET_PREFIX_RE.match(basefont):
                subsetted.add(basefont)

    return sorted(all_fonts), sorted(subsetted)


def _render_page0(doc: fitz.Document, dpi: int = 150) -> Image.Image:
    """Render page 0 as a PIL Image at the given DPI. Used by ViT + pHash."""
    if doc.page_count == 0:
        # 1x1 white placeholder — keeps downstream code from crashing on empty PDFs.
        return Image.new("RGB", (1, 1), color="white")

    page = doc.load_page(0)
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def parse_pdf(raw_bytes: bytes, *, render_dpi: int = 150) -> ParsedPDF:
    """Parse a PDF blob into a PDFMetadata + page-0 image + the same raw bytes.

    Raises ValueError if the bytes are not a valid PDF. Callers (workers/tasks.py)
    should catch this and mark the application FAILED.
    """
    if not raw_bytes or not raw_bytes.startswith(b"%PDF"):
        raise ValueError("Input is not a PDF (missing %PDF header)")

    with fitz.open(stream=raw_bytes, filetype="pdf") as doc:
        meta_dict = doc.metadata or {}
        producer = meta_dict.get("producer") or None
        creator = meta_dict.get("creator") or None
        category, _display = _classify_tool(producer, creator)
        all_fonts, subsetted = _extract_fonts(doc)
        page0 = _render_page0(doc, dpi=render_dpi)

        metadata = PDFMetadata(
            producer=producer,
            creator=creator,
            creation_date=_parse_pdf_date(meta_dict.get("creationDate")),
            modification_date=_parse_pdf_date(meta_dict.get("modDate")),
            title=meta_dict.get("title") or None,
            author=meta_dict.get("author") or None,
            page_count=doc.page_count,
            font_names=all_fonts,
            subsetted_fonts=subsetted,
            file_size_bytes=len(raw_bytes),
            tool_category=category,
        )

    logger.debug(
        "Parsed PDF | size={} bytes | pages={} | producer={!r} | category={}",
        metadata.file_size_bytes,
        metadata.page_count,
        metadata.producer,
        metadata.tool_category.value,
    )
    return ParsedPDF(metadata=metadata, page0_image=page0, raw_bytes=raw_bytes)
