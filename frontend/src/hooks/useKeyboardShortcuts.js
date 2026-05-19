import { useEffect, useState } from "react";

// Bind a map of keyboard shortcuts to global keydown. Ignores keypresses
// originating in form inputs (`input`, `textarea`, contenteditable) so the
// user never gets a "D" stolen mid-typing.
//
// `bindings` shape: { keyName: handler }
//   - keyName matches `event.key` directly (case-insensitive for single-char keys)
//   - Use "Escape", "Enter", etc. for non-character keys
//
// Modifier combos (Ctrl/Cmd/Alt) are passed through to the browser so the
// user can still use Ctrl+R to refresh, Cmd+K, etc.
export function useKeyboardShortcuts(bindings, { enabled = true } = {}) {
  useEffect(() => {
    if (!enabled) return undefined;

    const handler = (e) => {
      const target = e.target;
      const tag = target?.tagName?.toLowerCase();
      if (
        tag === "input" ||
        tag === "textarea" ||
        tag === "select" ||
        target?.isContentEditable
      ) {
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const fn = bindings[key] || bindings[e.key];
      if (typeof fn === "function") {
        e.preventDefault();
        fn(e);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [bindings, enabled]);
}

// Track the user's prefers-reduced-motion media query. Returns a boolean and
// updates if the OS preference changes during the session.
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" &&
    !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const listener = () => setReduced(mq.matches);
    mq.addEventListener?.("change", listener);
    return () => mq.removeEventListener?.("change", listener);
  }, []);
  return reduced;
}
