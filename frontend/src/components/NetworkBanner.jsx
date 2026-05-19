import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { WifiOff, X } from "lucide-react";

// Slim top-of-page banner shown when the WebSocket has been disconnected for
// long enough that it's not a transient blip. We wait `graceMs` before
// surfacing so the brief reconnect window between page loads doesn't flash
// a scary banner at the user.
export default function NetworkBanner({ wsStatus, graceMs = 4000 }) {
  const [visible, setVisible] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (wsStatus === "open") {
      setVisible(false);
      setDismissed(false);
      return undefined;
    }
    if (dismissed) return undefined;
    const t = setTimeout(() => setVisible(true), graceMs);
    return () => clearTimeout(t);
  }, [wsStatus, graceMs, dismissed]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: -40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -40, opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="sticky top-0 z-40 border-b border-signal-red/30 bg-signal-red/10"
        >
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-2 text-sm">
            <div className="flex items-center gap-2 text-signal-red">
              <WifiOff size={14} />
              <span>
                <strong className="font-semibold">Backend offline.</strong>{" "}
                Live events paused. Start the backend, or use{" "}
                <code className="font-mono text-xs">?demo=mock</code> on{" "}
                <span className="font-mono">/results</span> to preview.
              </span>
            </div>
            <button
              type="button"
              onClick={() => setDismissed(true)}
              className="inline-flex h-6 w-6 items-center justify-center rounded-full text-signal-red/80 transition-colors hover:bg-signal-red/10"
              aria-label="Dismiss"
            >
              <X size={13} />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
