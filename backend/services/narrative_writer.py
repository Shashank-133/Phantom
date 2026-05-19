"""Narrative writer — produces the English summary paragraph for a PHANTOM Report.

Two backends:
  1. Template (default). f-string. 100% reliable, zero network. The demo path.
  2. Gemini 1.5 Flash (optional, progressive enhancement). Used only when
     `GEMINI_API_KEY` is set AND `narrative_source="gemini"` is requested.

The LLM is **never** load-bearing. If the API key is missing, the call times
out, the response is malformed, or anything else goes wrong, we fall back to
the template — no error surfaces to the caller. The demo cannot fail because
of a third-party API.

Public surface:
  build_narrative(verdict, members, origin_summary, timing_summary) -> str
  narrative_source_info() -> {"backend": "template" | "gemini", "available": bool}
"""
from __future__ import annotations

import threading
from typing import Iterable

from loguru import logger

from config import get_settings
from schemas.phantom_report import RecommendedAction, RingMember
from services.cross_signal_engine import ClusterVerdict

# How long to wait for the Gemini Flash call before falling back. Tight; the
# demo is real-time and we'd rather a slightly-less-poetic narrative than a
# spinner.
GEMINI_TIMEOUT_SECONDS = 5.0
GEMINI_MODEL = "gemini-1.5-flash"


def _format_inr(amount: int) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.2f} crore"
    if amount >= 100_000:
        return f"₹{amount / 100_000:.2f} lakh"
    return f"₹{amount:,}"


def _verdict_phrases(action: RecommendedAction) -> tuple[str, str]:
    if action == RecommendedAction.FREEZE_AND_ESCALATE:
        return (
            "a coordinated fraud ring",
            "We recommend immediate freeze and escalation to the financial intelligence unit.",
        )
    if action == RecommendedAction.FLAG_FOR_REVIEW:
        return (
            "a suspected fraud cluster",
            "We recommend flagging for manual review before disbursement.",
        )
    return (
        "a cluster with weak fraud indicators",
        "Standard processing may continue with monitoring.",
    )


def _join_cities(cities: Iterable[str]) -> str:
    uniq = sorted({c for c in cities if c})
    if not uniq:
        return "multiple locations"
    if len(uniq) == 1:
        return uniq[0]
    if len(uniq) == 2:
        return f"{uniq[0]} and {uniq[1]}"
    return ", ".join(uniq[:-1]) + f", and {uniq[-1]}"


def _template_narrative(
    verdict: ClusterVerdict,
    members: list[RingMember],
    origin_summary: str,
    timing_summary: str,
) -> str:
    """The deterministic fallback. Always works."""
    n = len(members)
    cities = _join_cities(m.city for m in members)
    total = sum(m.loan_amount_inr for m in members)
    confidence_pct = round(verdict.phantom_score * 100, 1)
    ring_phrase, action_phrase = _verdict_phrases(verdict.recommended_action)

    return (
        f"PHANTOM analysis identified {ring_phrase} of {n} applicants operating "
        f"across {cities}, representing a combined credit exposure of "
        f"{_format_inr(total)}. {origin_summary} {timing_summary} "
        f"PHANTOM Confidence: {confidence_pct}%. {action_phrase}"
    )


# ---------------------------------------------------------------------------
# Optional Gemini path
# ---------------------------------------------------------------------------


_gemini_lock = threading.Lock()
_gemini_state = {"configured": False, "model": None}


def _gemini_model():
    """Lazy-configure google-generativeai exactly once per process."""
    with _gemini_lock:
        if _gemini_state["configured"]:
            return _gemini_state["model"]
        _gemini_state["configured"] = True
        settings = get_settings()
        api_key = (settings.gemini_api_key or "").strip()
        if not api_key:
            return None
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            _gemini_state["model"] = genai.GenerativeModel(GEMINI_MODEL)
            logger.info("Gemini narrative backend ready ({})", GEMINI_MODEL)
            return _gemini_state["model"]
        except Exception as e:
            logger.warning("Gemini configure failed — falling back to template: {}", e)
            return None


def _build_gemini_prompt(
    verdict: ClusterVerdict,
    members: list[RingMember],
    origin_summary: str,
    timing_summary: str,
) -> str:
    """A short, structured prompt. Asks for the same paragraph the template
    would have produced, but with naturalised English. Pinned facts go in;
    we never let the model invent numbers."""
    n = len(members)
    cities = _join_cities(m.city for m in members)
    total = sum(m.loan_amount_inr for m in members)
    confidence_pct = round(verdict.phantom_score * 100, 1)
    _, action_phrase = _verdict_phrases(verdict.recommended_action)
    return (
        "You are writing a single paragraph (4-6 sentences) of a fraud "
        "investigation report for a bank's compliance officer. Use the "
        "facts below verbatim — do not invent numbers, names, or signals. "
        "Tone: clipped, precise, no marketing language, no emojis, no "
        "headers. End with the action recommendation exactly as given.\n\n"
        f"- Cluster size: {n} applicants\n"
        f"- Cities: {cities}\n"
        f"- Total credit exposure: {_format_inr(total)}\n"
        f"- PHANTOM confidence: {confidence_pct}%\n"
        f"- Verdict: {verdict.recommended_action.value}\n"
        f"- Origin evidence: {origin_summary}\n"
        f"- Timing evidence: {timing_summary}\n"
        f"- Recommended action (use verbatim at the end): {action_phrase}\n"
    )


def _gemini_narrative(prompt: str) -> str | None:
    """Single Gemini call, bounded by GEMINI_TIMEOUT_SECONDS. Returns None on
    any failure — caller falls back to the template silently."""
    model = _gemini_model()
    if model is None:
        return None
    try:
        import concurrent.futures

        def _call():
            resp = model.generate_content(prompt)
            return (getattr(resp, "text", "") or "").strip()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_call)
            text = fut.result(timeout=GEMINI_TIMEOUT_SECONDS)

        if not text or len(text) < 80:
            return None
        return text
    except Exception as e:
        logger.warning("Gemini narrative call failed — falling back to template: {}", e)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_narrative(
    verdict: ClusterVerdict,
    members: list[RingMember],
    origin_summary: str,
    timing_summary: str,
    *,
    prefer_gemini: bool = True,
) -> str:
    """Return the narrative paragraph. Tries Gemini if available, else template."""
    if prefer_gemini and (get_settings().gemini_api_key or "").strip():
        prompt = _build_gemini_prompt(verdict, members, origin_summary, timing_summary)
        text = _gemini_narrative(prompt)
        if text:
            return text
    return _template_narrative(verdict, members, origin_summary, timing_summary)


def narrative_source_info() -> dict:
    """For /health — what narrative backend is the server currently capable of?"""
    settings = get_settings()
    has_key = bool((settings.gemini_api_key or "").strip())
    return {
        "backend": "gemini" if has_key else "template",
        "gemini_available": has_key,
        "gemini_model": GEMINI_MODEL if has_key else None,
    }
