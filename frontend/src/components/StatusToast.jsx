import { AnimatePresence, motion } from "framer-motion";
import { Loader2, CheckCircle2, AlertCircle, Activity } from "lucide-react";

// Floating live-status pill. Shows current pipeline stage during analysis.
// Pinned to the bottom-right so it stays in view while the user scrolls
// through results.
export default function StatusToast({ wsStatus, analyzed, total, isComplete, ringCount }) {
  let label;
  let Icon;
  let tone;
  if (wsStatus !== "open" && analyzed === 0) {
    return null;
  }
  if (isComplete) {
    label =
      ringCount > 0
        ? `Analysis complete · ${ringCount} ring${ringCount > 1 ? "s" : ""} detected`
        : "Analysis complete · no rings";
    Icon = ringCount > 0 ? AlertCircle : CheckCircle2;
    tone = ringCount > 0 ? "text-signal-red" : "text-signal-green";
  } else if (total > 0) {
    label = `Analysing ${analyzed}/${total} applications`;
    Icon = Loader2;
    tone = "text-ink";
  } else {
    label = "Waiting for events…";
    Icon = Activity;
    tone = "text-ink-muted";
  }

  return (
    <AnimatePresence>
      <motion.div
        key={label}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 16 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-3 rounded-full border border-border-strong bg-cream-bg/95 px-5 py-3 shadow-sm backdrop-blur"
      >
        <Icon
          size={16}
          className={`${tone} ${!isComplete && Icon === Loader2 ? "animate-spin" : ""}`}
        />
        <span className="text-sm font-medium text-ink">{label}</span>
      </motion.div>
    </AnimatePresence>
  );
}
