import { motion } from "framer-motion";
import { FileText, ShieldAlert, ShieldCheck } from "lucide-react";
import { pct } from "../lib/formatters";

// One row per analysed application. The CBS-match score is the headline
// number — high = looks like a real bank document, low = looks like Canva.
// Tool badge is the producer-string classification from origin_engine.
function toolBadge(tool) {
  if (!tool) return null;
  const consumer = ["Canva", "Word", "Photoshop", "Other"].some((s) =>
    String(tool).toLowerCase().includes(s.toLowerCase())
  );
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wider ${
        consumer
          ? "border border-signal-red/30 bg-signal-red/8 text-signal-red"
          : "border border-signal-green/30 bg-signal-green/8 text-signal-green"
      }`}
    >
      {tool}
    </span>
  );
}

export default function ApplicationCard({ event, index = 0 }) {
  const score = event.cbs_match_score ?? event.origin_match_score;
  const suspicious = score != null && score < 0.6;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(index * 0.015, 0.3) }}
      className="card flex items-center gap-4 px-5 py-3 transition-colors duration-200 hover:border-border-strong hover:bg-cream-alt/40"
    >
      <div
        className={`inline-flex h-10 w-10 items-center justify-center rounded-lg ${
          suspicious ? "bg-signal-red/10 text-signal-red" : "bg-cream-alt text-ink"
        }`}
      >
        {suspicious ? <ShieldAlert size={18} /> : <FileText size={18} />}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-ink">
            {event.applicant_name || "Unknown applicant"}
          </p>
          {toolBadge(event.origin_tool)}
        </div>
        <p className="mt-0.5 text-xs text-ink-muted">
          {event.progress ? `${event.progress} · ` : ""}
          {event.application_id
            ? `#${String(event.application_id).slice(0, 8)}`
            : ""}
        </p>
      </div>

      <div className="text-right">
        <p
          className={`font-mono text-sm tabular-nums ${
            suspicious ? "text-signal-red" : "text-ink"
          }`}
        >
          {pct(score)}
        </p>
        <p className="text-[0.65rem] uppercase tracking-wider text-ink-muted">
          CBS match
        </p>
      </div>

      {!suspicious && (
        <ShieldCheck size={18} className="text-signal-green" aria-hidden />
      )}
    </motion.div>
  );
}
