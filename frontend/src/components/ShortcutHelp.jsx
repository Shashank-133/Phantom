import { AnimatePresence, motion } from "framer-motion";
import { Keyboard, X } from "lucide-react";

const SHORTCUTS = [
  { keys: ["D"], label: "Run the demo (from Analyse page)" },
  { keys: ["R"], label: "Replay the cinematic reveal (Results)" },
  { keys: ["Esc"], label: "Close the origin-tree drawer" },
  { keys: ["?"], label: "Toggle this shortcut list" },
];

function KeyCap({ children }) {
  return (
    <kbd className="inline-flex min-w-[1.6rem] items-center justify-center rounded-md border border-border-strong bg-cream-bg px-2 py-0.5 font-mono text-[0.7rem] font-medium text-ink shadow-[inset_0_-1px_0_rgba(0,0,0,0.05)]">
      {children}
    </kbd>
  );
}

export default function ShortcutHelp({ open, onClose }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[2px]"
          />
          <motion.div
            key="dialog"
            initial={{ opacity: 0, y: 16, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.97 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            className="fixed left-1/2 top-1/2 z-50 w-[min(90vw,28rem)] -translate-x-1/2 -translate-y-1/2 rounded-card border border-border-strong bg-cream-bg p-6"
          >
            <div className="mb-5 flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <Keyboard size={16} className="text-ink-muted" />
                <h3 className="text-base font-semibold text-ink">
                  Keyboard shortcuts
                </h3>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-7 w-7 items-center justify-center rounded-full text-ink-muted transition-colors hover:bg-cream-alt"
                aria-label="Close"
              >
                <X size={13} />
              </button>
            </div>
            <ul className="space-y-2.5">
              {SHORTCUTS.map((s) => (
                <li
                  key={s.label}
                  className="flex items-center justify-between gap-4"
                >
                  <span className="text-sm text-ink-muted">{s.label}</span>
                  <span className="flex shrink-0 items-center gap-1">
                    {s.keys.map((k) => (
                      <KeyCap key={k}>{k}</KeyCap>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-5 border-t border-border-light pt-4 text-xs text-ink-muted">
              Shortcuts are inactive while typing in a form field.
            </p>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
