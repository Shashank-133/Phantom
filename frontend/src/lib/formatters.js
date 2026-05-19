// Currency in Indian lakh/crore units — what a Canara Bank judge expects.
export function formatINR(amount) {
  if (amount == null || Number.isNaN(amount)) return "—";
  const n = Number(amount);
  if (n >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(2)} crore`;
  if (n >= 1_00_000) return `₹${(n / 1_00_000).toFixed(2)} lakh`;
  return `₹${n.toLocaleString("en-IN")}`;
}

// Truncate a long hex hash for display: keep the first 8 + last 6 chars.
export function shortHash(hash) {
  if (!hash) return "";
  if (hash.length <= 16) return hash;
  return `${hash.slice(0, 8)}…${hash.slice(-6)}`;
}

// Percentage with one decimal place — what scores look like on the dashboard.
export function pct(score) {
  if (score == null || Number.isNaN(score)) return "—";
  return `${(Number(score) * 100).toFixed(1)}%`;
}

// Friendly relative time (only used for very recent events; full timestamps
// are formatted by Intl.DateTimeFormat directly where needed).
export function relativeTime(isoString) {
  if (!isoString) return "";
  const then = new Date(isoString).getTime();
  const diff = Date.now() - then;
  const s = Math.floor(diff / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(isoString).toLocaleDateString("en-IN");
}

// Pretty label for the verdict enum.
export function verdictLabel(action) {
  switch (action) {
    case "FREEZE_AND_ESCALATE":
      return "Freeze & escalate";
    case "FLAG_FOR_REVIEW":
      return "Flag for review";
    case "CLEAR":
      return "Clear";
    default:
      return action || "—";
  }
}
