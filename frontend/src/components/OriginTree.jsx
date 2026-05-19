import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  FileText,
  Cpu,
  Activity,
  Type,
  Hash,
  Calendar,
  AlertTriangle,
  BadgeCheck,
} from "lucide-react";
import { colors } from "../theme/colors";
import { pct, formatINR } from "../lib/formatters";

// Forensic drill-down for a single applicant. Slides in from the right when
// a node in FraudGraph is clicked. Shows the four origin signals (producer,
// font subsetting, entropy profile, ViT-vs-CBS distance) plus identity meta.
//
// Tolerant of sparse data — the live WebSocket-derived graph node only
// carries a few fields, but the structure renders fine when most are null.

function EntropyBar({ value }) {
  // 8-bucket Shannon entropy. CBS-like docs spike unevenly (variance > 0.8),
  // consumer designers (Canva) are flat / smooth. The chart is a tiny visual
  // hint at that pattern, not a precise readout.
  const v = Math.max(0, Math.min(1, value || 0));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-cream-alt">
      <div
        className="h-full rounded-full bg-ink"
        style={{ width: `${v * 100}%` }}
      />
    </div>
  );
}

function ToolVerdict({ tool }) {
  if (!tool) return null;
  const isConsumer = ["Canva", "Word", "Photoshop", "Other"].some((s) =>
    String(tool).toLowerCase().includes(s.toLowerCase())
  );
  return (
    <div
      className="mt-3 flex items-center gap-2 rounded-md border px-3 py-2 text-xs"
      style={{
        borderColor: isConsumer ? `${colors.signal.red}40` : `${colors.signal.green}40`,
        backgroundColor: isConsumer ? `${colors.signal.red}08` : `${colors.signal.green}08`,
        color: isConsumer ? colors.signal.red : colors.signal.green,
      }}
    >
      {isConsumer ? <AlertTriangle size={13} /> : <BadgeCheck size={13} />}
      <span>
        {isConsumer
          ? "Consumer design tool — not a Core Banking System."
          : "Producer matches a known Core Banking System."}
      </span>
    </div>
  );
}

export default function OriginTree({ node, onClose }) {
  return (
    <AnimatePresence>
      {node && (
        <>
          {/* Backdrop — click anywhere outside to close */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-sm"
          />
          <motion.aside
            key="panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            role="dialog"
            aria-modal="true"
            aria-label="Origin tree drill-down"
            className="fixed right-0 top-0 z-50 flex h-[100dvh] w-full flex-col overflow-y-auto border-l border-border-strong bg-cream-bg p-5 sm:max-w-md sm:p-7"
          >
            <div className="mb-5 flex items-start justify-between gap-3">
              <div>
                <p className="text-[0.65rem] font-medium uppercase tracking-[0.22em] text-ink-muted">
                  Origin tree
                </p>
                <h3 className="mt-1 font-serif text-2xl italic text-ink">
                  {node.name || node.applicant_name || "Unknown applicant"}
                </h3>
                {node.city && (
                  <p className="mt-0.5 text-sm text-ink-muted">{node.city}</p>
                )}
              </div>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border-light text-ink-muted transition-colors hover:bg-cream-alt"
                aria-label="Close"
              >
                <X size={15} />
              </button>
            </div>

            {/* Verdict strip */}
            {node.in_ring && (
              <div
                className="mb-5 rounded-card border px-4 py-3 text-sm"
                style={{
                  borderColor: `${colors.signal.red}40`,
                  backgroundColor: `${colors.signal.red}08`,
                  color: colors.signal.red,
                }}
              >
                <p className="font-semibold">Member of detected fraud ring</p>
                <p className="mt-0.5 text-xs opacity-80">
                  Multiple cross-signal edges link this applicant to a
                  confirmed cluster.
                </p>
              </div>
            )}

            {/* Identity */}
            <section>
              <p className="mb-3 text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
                Application
              </p>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <dt className="text-ink-muted">Application ID</dt>
                <dd className="font-mono text-ink truncate">
                  {(node.id || node.application_id || "—").slice(0, 14)}…
                </dd>
                <dt className="text-ink-muted">Loan amount</dt>
                <dd className="font-mono text-ink tabular-nums">
                  {formatINR(node.amount || node.loan_amount_inr)}
                </dd>
                {node.submission_time && (
                  <>
                    <dt className="text-ink-muted">Submitted</dt>
                    <dd className="font-mono text-ink">
                      {new Date(node.submission_time).toLocaleString("en-IN", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </dd>
                  </>
                )}
              </dl>
            </section>

            {/* Engine 1 — document origin signals */}
            <section className="mt-7">
              <div className="mb-3 flex items-center gap-2">
                <Cpu size={14} className="text-ink-muted" />
                <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
                  Engine 1 · document origin
                </p>
              </div>

              {/* Producer tool */}
              <div>
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-ink-muted">
                    <FileText size={13} />
                    PDF producer
                  </span>
                  <span className="font-mono text-ink">
                    {node.origin_tool || "—"}
                  </span>
                </div>
                <ToolVerdict tool={node.origin_tool} />
              </div>

              {/* CBS match */}
              <div className="mt-5">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-ink-muted">
                    <Activity size={13} />
                    CBS match score
                  </span>
                  <span
                    className="font-mono tabular-nums text-ink"
                    style={{
                      color:
                        node.cbs_match_score != null && node.cbs_match_score < 0.6
                          ? colors.signal.red
                          : colors.ink.DEFAULT,
                    }}
                  >
                    {pct(node.cbs_match_score)}
                  </span>
                </div>
                <div className="mt-1.5">
                  <EntropyBar value={node.cbs_match_score} />
                </div>
                <p className="mt-1.5 text-xs text-ink-muted">
                  Distance from the 100-document CBS reference centroid. Low =
                  document looks unlike anything a real CBS would produce.
                </p>
              </div>

              {/* Font subset hash */}
              {node.font_subset_hash && (
                <div className="mt-5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 text-ink-muted">
                      <Type size={13} />
                      Font subset hash
                    </span>
                  </div>
                  <p className="mt-1.5 font-mono text-xs text-ink break-all">
                    {node.font_subset_hash}
                  </p>
                  <p className="mt-1.5 text-xs text-ink-muted">
                    Pre-subsetted fonts (AAAAAA+ArialMT) are evidence of an
                    enterprise rendering toolchain. Built-in core fonts
                    (Helvetica) indicate consumer tools.
                  </p>
                </div>
              )}

              {/* Document creation timestamp */}
              {node.creation_timestamp && (
                <div className="mt-5 flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-ink-muted">
                    <Calendar size={13} />
                    File created at
                  </span>
                  <span className="font-mono text-ink">
                    {new Date(node.creation_timestamp).toLocaleString("en-IN")}
                  </span>
                </div>
              )}
            </section>

            {/* Engine 2 — network signals (mostly contextual; the graph IS Engine 2) */}
            <section className="mt-7">
              <div className="mb-3 flex items-center gap-2">
                <Hash size={14} className="text-ink-muted" />
                <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
                  Engine 2 · network position
                </p>
              </div>
              <p className="text-sm leading-relaxed text-ink-muted">
                {node.in_ring
                  ? "Lives inside the detected community. Multiple template, PII, and timing edges to fellow ring members."
                  : "No suspicious cluster membership. Sparse, unrelated edges to other applicants."}
              </p>
            </section>

            <div className="mt-auto pt-8">
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary w-full"
              >
                Close
              </button>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
