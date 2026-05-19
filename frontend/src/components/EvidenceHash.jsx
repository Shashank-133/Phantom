import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { shortHash } from "../lib/formatters";

// Monospace hash / key-id chip with copy button. Used wherever an Ed25519
// signature, evidence SHA-256, or key identifier is displayed.
export default function EvidenceHash({ label, value, full = false }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard blocked — silently no-op */
    }
  };

  return (
    <div className="inline-flex items-center gap-2 rounded-md border border-border-light bg-cream-alt px-2.5 py-1.5">
      {label && (
        <span className="text-[0.65rem] uppercase tracking-wider text-ink-muted">
          {label}
        </span>
      )}
      <code className="font-mono text-xs text-ink">
        {full ? value : shortHash(value)}
      </code>
      <button
        type="button"
        onClick={onCopy}
        className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded text-ink-muted transition-colors hover:bg-cream-bg hover:text-ink"
        aria-label="Copy hash"
      >
        {copied ? <Check size={12} /> : <Copy size={12} />}
      </button>
    </div>
  );
}
