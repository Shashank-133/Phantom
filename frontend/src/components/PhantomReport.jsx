import { motion } from "framer-motion";
import { AlertCircle, Download, FileSignature, FileText } from "lucide-react";
import EvidenceHash from "./EvidenceHash";
import { formatINR, pct, verdictLabel } from "../lib/formatters";
import { verdictColor } from "../theme/colors";
import { api } from "../lib/api";

// The "court-ready" panel that slides in alongside the fraud graph once a
// ring is confirmed. Styled to feel like a printed document, not a dashboard:
// generous serif headings, paper-card background, monospace for hashes.
//
// Reads everything from a single PHANTOMReport payload (matches backend
// schemas/phantom_report.py). Tolerant of partial payloads from the mock
// generator — missing fields render as "—" rather than crashing.

function MetaRow({ label, value, mono }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border-light py-2 last:border-b-0">
      <span className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
        {label}
      </span>
      <span
        className={`text-sm text-ink ${
          mono ? "font-mono tabular-nums" : ""
        }`}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

export default function PhantomReport({ ring, className = "" }) {
  if (!ring) return null;
  const action = ring.recommended_action || ring.action;
  const accent = verdictColor(action);
  const confidence =
    ring.phantom_confidence_pct ??
    (ring.phantom_score != null ? Math.round(ring.phantom_score * 100) : null);
  const evidence = ring.evidence_bundle || {};

  return (
    <motion.aside
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className={`card flex flex-col bg-cream-bg p-7 ${className}`}
    >
      {/* Document header — looks like the top of a printed report */}
      <header className="mb-6 border-b border-border-strong pb-5">
        <div className="flex items-center justify-between">
          <p className="text-[0.65rem] font-medium uppercase tracking-[0.22em] text-ink-muted">
            PHANTOM Report
          </p>
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.65rem] font-medium uppercase tracking-[0.14em]"
            style={{
              backgroundColor: `${accent}14`,
              color: accent,
              border: `1px solid ${accent}40`,
            }}
          >
            <AlertCircle size={11} />
            {verdictLabel(action)}
          </span>
        </div>
        <h2 className="mt-3 font-serif text-3xl italic text-ink">
          {ring.ring_size}-applicant ring
        </h2>
        <p className="mt-1 font-mono text-xs text-ink-muted">
          {ring.ring_id}
        </p>
      </header>

      {/* Top-line stats */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
            Confidence
          </p>
          <p
            className="mt-1 font-mono text-2xl tabular-nums"
            style={{ color: accent }}
          >
            {confidence != null ? `${confidence}%` : "—"}
          </p>
        </div>
        <div>
          <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
            Exposure
          </p>
          <p className="mt-1 font-mono text-2xl tabular-nums text-ink">
            {formatINR(ring.total_exposure_inr)}
          </p>
        </div>
        <div>
          <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
            Ring size
          </p>
          <p className="mt-1 font-mono text-2xl tabular-nums text-ink">
            {ring.ring_size ?? ring.members?.length ?? "—"}
          </p>
        </div>
      </div>

      {/* Narrative — the human-readable summary */}
      {ring.narrative && (
        <p className="mt-7 text-base leading-relaxed text-ink-muted">
          {ring.narrative}
        </p>
      )}

      {/* Origin + timing summary */}
      <div className="mt-7 space-y-5">
        {ring.origin_summary && (
          <div>
            <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
              Origin summary
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
              {ring.origin_summary}
            </p>
          </div>
        )}
        {ring.timing_summary && (
          <div>
            <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
              Timing summary
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
              {ring.timing_summary}
            </p>
          </div>
        )}
      </div>

      {/* Component score breakdown */}
      <div className="mt-7 rounded-card border border-border-light bg-cream-alt/40 p-4">
        <p className="mb-3 text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
          Score breakdown
        </p>
        <div className="grid grid-cols-2 gap-x-6">
          <MetaRow label="Behavioural" value={pct(ring.behavioral_score ?? evidence.behavioral_score)} mono />
          <MetaRow label="Origin match" value={pct(ring.origin_match_score ?? evidence.origin_match_score)} mono />
          <MetaRow label="Template" value={pct(evidence.template_match_fraction)} mono />
          <MetaRow label="Timing burst" value={pct(evidence.timing_burst_score)} mono />
          <MetaRow label="Same tool" value={pct(evidence.same_tool_fraction)} mono />
          <MetaRow label="Font hash" value={pct(evidence.font_hash_match_fraction)} mono />
          <MetaRow label="PII overlap" value={pct(evidence.pii_overlap_fraction)} mono />
          <MetaRow label="Text similarity" value={pct(evidence.text_similarity_fraction)} mono />
        </div>
      </div>

      {/* Members list */}
      {ring.members && ring.members.length > 0 && (
        <div className="mt-7">
          <p className="mb-2 text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
            Ring members ({ring.members.length})
          </p>
          <ul className="max-h-52 space-y-1 overflow-y-auto pr-1">
            {ring.members.map((m, i) => (
              <li
                key={(m.application_id || m.id || m.name) + "-" + i}
                className="flex items-center justify-between rounded-md border border-border-light bg-cream-alt/40 px-3 py-1.5 text-xs"
              >
                <div className="flex flex-col">
                  <span className="text-ink">
                    {m.applicant_name || m.name || "Unknown"}
                  </span>
                  {m.city && (
                    <span className="text-ink-muted">{m.city}</span>
                  )}
                </div>
                <span className="font-mono text-ink-muted">
                  {formatINR(m.loan_amount_inr)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Signed evidence footer */}
      <footer className="mt-7 border-t border-border-strong pt-5">
        <div className="mb-3 flex items-center gap-2">
          <FileSignature size={14} className="text-ink-muted" />
          <span className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
            Signed evidence (Ed25519)
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {ring.evidence_hash_sha256 && (
            <EvidenceHash label="SHA-256" value={ring.evidence_hash_sha256} />
          )}
          {ring.signing_key_id && (
            <EvidenceHash label="Key ID" value={ring.signing_key_id} full />
          )}
        </div>
        <div className="mt-5 grid gap-2 sm:grid-cols-2">
          <a
            href={api.evidencePdfUrl(ring.ring_id)}
            download
            className="btn-primary"
          >
            <FileText size={15} />
            PDF report
          </a>
          <a
            href={api.evidenceUrl(ring.ring_id)}
            download
            className="btn-secondary"
          >
            <Download size={15} />
            Signed JSON
          </a>
        </div>
        <p className="mt-3 text-[0.65rem] uppercase tracking-[0.15em] text-ink-muted">
          Verify with{" "}
          <a
            href={api.publicKeyUrl()}
            className="underline-offset-2 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            /evidence/public-key
          </a>
        </p>
      </footer>
    </motion.aside>
  );
}
