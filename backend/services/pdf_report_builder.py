"""PHANTOM Report PDF builder.

Renders a polished, court-ready PDF from a PHANTOMReport object. Uses
ReportLab (no GTK / weasyprint dependency — installs cleanly on Windows).

The visual language matches the frontend's "coldiq cream" theme:
  * Cream A4 background
  * Near-black serif headings + sans body
  * Coloured strip up top encoding the verdict (red/amber/green)
  * Monospace block at the foot containing the Ed25519 signature

Return value is `bytes` so callers (the FastAPI evidence route, or a CLI
exporter) can stream / save without hitting disk.
"""
from __future__ import annotations

import io
from datetime import datetime

from loguru import logger
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from schemas.phantom_report import PHANTOMReport, RecommendedAction

# ---- Theme tokens (mirrors frontend/tailwind.config.js) ----
CREAM_BG = colors.HexColor("#FAF5EA")
CREAM_ALT = colors.HexColor("#F4EDDD")
BORDER_LIGHT = colors.HexColor("#E8DFCB")
BORDER_STRONG = colors.HexColor("#D8CDB5")
INK = colors.HexColor("#1A1A1A")
INK_MUTED = colors.HexColor("#6B655C")
SIGNAL_RED = colors.HexColor("#C8321F")
SIGNAL_AMBER = colors.HexColor("#D4953A")
SIGNAL_GREEN = colors.HexColor("#5C8A4A")
ACCENT = colors.HexColor("#4A8BC7")


def _verdict_color(action: RecommendedAction):
    if action == RecommendedAction.FREEZE_AND_ESCALATE:
        return SIGNAL_RED
    if action == RecommendedAction.FLAG_FOR_REVIEW:
        return SIGNAL_AMBER
    return SIGNAL_GREEN


def _fmt_inr(amount: int) -> str:
    if amount >= 10_000_000:
        return f"INR {amount / 10_000_000:.2f} Cr"
    if amount >= 100_000:
        return f"INR {amount / 100_000:.2f} L"
    return f"INR {amount:,}"


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


# ---- Reusable paragraph styles ----


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "kicker",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=INK_MUTED,
            spaceAfter=2,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Times-Italic",
            fontSize=26,
            leading=30,
            textColor=INK,
            spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=INK,
            spaceBefore=14,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=INK,
            spaceAfter=6,
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13.5,
            textColor=INK_MUTED,
            spaceAfter=4,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8,
            leading=10.5,
            textColor=INK,
        ),
        "mono_small": ParagraphStyle(
            "mono_small",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7,
            leading=9.5,
            textColor=INK_MUTED,
        ),
        "verdict": ParagraphStyle(
            "verdict",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.white,
        ),
    }


# ---- Page chrome (header + footer painted by canvas) ----


def _make_canvas_painter(report: PHANTOMReport):
    """Returns the function ReportLab calls on every page render."""
    accent = _verdict_color(report.recommended_action)
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    def paint(canvas: Canvas, doc):
        width, height = A4

        # Cream background fill
        canvas.saveState()
        canvas.setFillColor(CREAM_BG)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)

        # Verdict strip
        canvas.setFillColor(accent)
        canvas.rect(0, height - 6 * mm, width, 6 * mm, fill=1, stroke=0)

        # Wordmark + meta header band
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(20 * mm, height - 14 * mm, "PHANTOM")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(INK_MUTED)
        canvas.drawString(
            38 * mm,
            height - 14 * mm,
            "Fraud Ring & Document Origin Intelligence",
        )
        canvas.drawRightString(
            width - 20 * mm, height - 14 * mm, f"Ring {report.ring_id}"
        )

        # Page footer — number, generated-at, key id
        canvas.setFillColor(INK_MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(20 * mm, 12 * mm, f"Generated {generated}")
        canvas.drawCentredString(
            width / 2,
            12 * mm,
            f"Key ID {report.signing_key_id}",
        )
        canvas.drawRightString(
            width - 20 * mm, 12 * mm, f"Page {doc.page}"
        )
        # 1px horizontal divider above the footer
        canvas.setStrokeColor(BORDER_LIGHT)
        canvas.setLineWidth(0.4)
        canvas.line(20 * mm, 16 * mm, width - 20 * mm, 16 * mm)

        canvas.restoreState()

    return paint


# ---- Section builders ----


def _verdict_banner(report: PHANTOMReport, styles: dict) -> Table:
    accent = _verdict_color(report.recommended_action)
    label_map = {
        RecommendedAction.FREEZE_AND_ESCALATE: "FREEZE & ESCALATE",
        RecommendedAction.FLAG_FOR_REVIEW: "FLAG FOR REVIEW",
        RecommendedAction.CLEAR: "CLEAR",
    }
    cells = [
        [
            Paragraph(label_map[report.recommended_action], styles["verdict"]),
            Paragraph(
                f"<font color='#1A1A1A'><b>{report.phantom_confidence_pct:.1f}% confidence</b></font> "
                f"<font color='#6B655C'>· {report.ring_size} applicants · "
                f"{_fmt_inr(report.total_exposure_inr)} exposure</font>",
                ParagraphStyle(
                    "banner_body",
                    fontName="Helvetica",
                    fontSize=9,
                    leading=12,
                    textColor=INK,
                ),
            ),
        ]
    ]
    tbl = Table(cells, colWidths=[40 * mm, None])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), accent),
                ("BACKGROUND", (1, 0), (1, 0), CREAM_ALT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_STRONG),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return tbl


def _score_table(report: PHANTOMReport, styles: dict) -> Table:
    """11-row table showing every component score with its label."""
    eb = report.evidence_bundle
    rows = [
        ["Component", "Score", "Component", "Score"],
        ["Behavioral score", _pct(eb.behavioral_score), "Origin match score", _pct(eb.origin_match_score)],
        ["Timing burst", _pct(eb.timing_burst_score), "Same tool", _pct(eb.same_tool_fraction)],
        ["Template match", _pct(eb.template_match_fraction), "Entropy similarity", _pct(eb.entropy_similarity)],
        ["Cluster size", _pct(eb.cluster_size_score), "Font hash match", _pct(eb.font_hash_match_fraction)],
        ["PII overlap", _pct(eb.pii_overlap_fraction), "Text similarity", _pct(eb.text_similarity_fraction)],
        ["Name similarity", _pct(eb.name_similarity_fraction), "", ""],
    ]
    tbl = Table(rows, colWidths=[50 * mm, 25 * mm, 50 * mm, 25 * mm])
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), INK_MUTED),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("FONTNAME", (1, 1), (1, -1), "Courier"),
                ("FONTNAME", (3, 1), (3, -1), "Courier"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER_STRONG),
                ("LINEBELOW", (0, 1), (-1, -2), 0.25, BORDER_LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tbl


def _members_table(report: PHANTOMReport, styles: dict) -> Table:
    rows = [["#", "Applicant", "City", "Loan amount", "Submitted", "CBS match", "Tool"]]
    for i, m in enumerate(report.evidence_bundle.members, start=1):
        rows.append(
            [
                str(i),
                m.applicant_name,
                m.city,
                _fmt_inr(m.loan_amount_inr),
                m.submission_time.strftime("%Y-%m-%d %H:%M"),
                f"{m.cbs_match_score:.2f}",
                m.origin_tool,
            ]
        )
    tbl = Table(
        rows,
        colWidths=[8 * mm, 38 * mm, 22 * mm, 28 * mm, 28 * mm, 18 * mm, 28 * mm],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), INK_MUTED),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("ALIGN", (5, 0), (5, -1), "RIGHT"),
                ("FONTNAME", (3, 1), (3, -1), "Courier"),
                ("FONTNAME", (4, 1), (4, -1), "Courier"),
                ("FONTNAME", (5, 1), (5, -1), "Courier"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER_STRONG),
                ("LINEBELOW", (0, 1), (-1, -2), 0.25, BORDER_LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    return tbl


def _signature_block(report: PHANTOMReport, styles: dict) -> Table:
    """Footer block displaying the SHA-256 + Ed25519 signature + verification note."""
    # Wrap long values so they fit the column width.
    sig = report.evidence_signature_ed25519
    sig_chunks = [sig[i : i + 64] for i in range(0, len(sig), 64)]
    rows = [
        [
            Paragraph("ALGORITHM", styles["kicker"]),
            Paragraph("Ed25519 (RFC 8032)", styles["mono"]),
        ],
        [
            Paragraph("KEY ID", styles["kicker"]),
            Paragraph(report.signing_key_id, styles["mono"]),
        ],
        [
            Paragraph("SHA-256", styles["kicker"]),
            Paragraph(report.evidence_hash_sha256, styles["mono"]),
        ],
        [
            Paragraph("SIGNATURE", styles["kicker"]),
            Paragraph("<br/>".join(sig_chunks), styles["mono"]),
        ],
        [
            Paragraph("VERIFY", styles["kicker"]),
            Paragraph(
                "Fetch the bank's Ed25519 public key from /evidence/public-key. "
                "Canonical-JSON encode the evidence bundle (sort_keys=True, no "
                "whitespace) and verify the signature against the canonical "
                "bytes. Any modification invalidates this report.",
                styles["muted"],
            ),
        ],
    ]
    tbl = Table(rows, colWidths=[28 * mm, None])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CREAM_ALT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_STRONG),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEABOVE", (0, 1), (-1, -1), 0.25, BORDER_LIGHT),
            ]
        )
    )
    return tbl


# ---- Public API ----


def build_phantom_report_pdf(report: PHANTOMReport) -> bytes:
    """Render a PHANTOMReport to a polished PDF and return the bytes."""
    buf = io.BytesIO()
    styles = _styles()

    # Custom doc template so we can paint the cream background + verdict strip.
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"PHANTOM Report — {report.ring_id}",
        author="PHANTOM",
        subject="Fraud ring evidence bundle",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="content",
    )
    template = PageTemplate(
        id="phantom",
        frames=[frame],
        onPage=_make_canvas_painter(report),
    )
    doc.addPageTemplates([template])

    story = []

    story.append(Paragraph("PHANTOM REPORT", styles["kicker"]))
    story.append(Paragraph(f"{report.ring_size}-applicant ring", styles["h1"]))
    story.append(
        Paragraph(
            f"<font color='#6B655C'>Detected {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')} · "
            f"{report.ring_id}</font>",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(_verdict_banner(report, styles))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Summary", styles["h2"]))
    story.append(Paragraph(report.narrative, styles["body"]))

    story.append(Paragraph("Document origin", styles["h2"]))
    story.append(Paragraph(report.origin_summary, styles["body"]))

    story.append(Paragraph("Timing", styles["h2"]))
    story.append(Paragraph(report.timing_summary, styles["body"]))

    story.append(Paragraph("Score breakdown", styles["h2"]))
    story.append(_score_table(report, styles))

    story.append(Paragraph("Ring members", styles["h2"]))
    story.append(_members_table(report, styles))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Signed evidence", styles["h2"]))
    story.append(_signature_block(report, styles))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    logger.info(
        "PDF report rendered | ring={} | size={} bytes | pages~{}",
        report.ring_id,
        len(pdf_bytes),
        max(1, len(pdf_bytes) // 30_000),
    )
    return pdf_bytes
