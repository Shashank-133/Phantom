// Exported JS mirror of the Tailwind palette. Used by non-Tailwind consumers —
// D3 attribute values, Framer Motion animations, dynamic inline styles.
// Editing here without editing tailwind.config.js will desync — change both.
export const colors = {
  cream: {
    bg: "#FAF5EA",
    alt: "#F4EDDD",
    dim: "#D4CFC2",
  },
  border: {
    light: "#E8DFCB",
    strong: "#D8CDB5",
  },
  ink: {
    DEFAULT: "#1A1A1A",
    muted: "#6B655C",
    placeholder: "#9A938A",
  },
  accent: "#4A8BC7",
  signal: {
    red: "#C8321F",
    amber: "#D4953A",
    green: "#5C8A4A",
  },
};

// Verdict → colour mapping. Keeps the rule in one place.
export function verdictColor(action) {
  if (action === "FREEZE_AND_ESCALATE") return colors.signal.red;
  if (action === "FLAG_FOR_REVIEW") return colors.signal.amber;
  return colors.signal.green;
}
