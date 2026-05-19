/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // PHANTOM "coldiq cream" palette — all tokens, never raw hex in components.
        // Single source of truth; change here and the whole app reskins.
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
        accent: {
          DEFAULT: "#4A8BC7",
        },
        signal: {
          red: "#C8321F",
          amber: "#D4953A",
          green: "#5C8A4A",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        serif: [
          "Instrument Serif",
          "Cormorant Garamond",
          "ui-serif",
          "Georgia",
          "serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      fontSize: {
        // Editorial scale — generous, matches coldiq/autoaudit hero proportions
        "display-xl": ["clamp(3rem, 7vw, 6rem)", { lineHeight: "1.05", letterSpacing: "-0.025em" }],
        "display-lg": ["clamp(2.25rem, 5vw, 4.25rem)", { lineHeight: "1.1", letterSpacing: "-0.02em" }],
        "display-md": ["clamp(1.75rem, 3.5vw, 2.75rem)", { lineHeight: "1.15", letterSpacing: "-0.015em" }],
      },
      borderRadius: {
        card: "12px",
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
