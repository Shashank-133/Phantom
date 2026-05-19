import { useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { api } from "../lib/api";

// Single-click trigger for the 40-applicant seeded pipeline. This is the
// stage demo's safety net — no upload step, no chance of a bad file. The
// `reset` toggle re-creates the demo data from scratch (useful between
// rehearsals when graph state from a previous run should be wiped).
export default function DemoModeButton({ onStarted, reset = true, className = "" }) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const run = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await api.startDemo({ reset });
      onStarted?.(res);
    } catch (e) {
      setErr(e.message || "Failed to start demo");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`flex flex-col items-stretch gap-2 ${className}`}>
      <button
        type="button"
        onClick={run}
        disabled={loading}
        className="btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {loading ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            <span>Starting…</span>
          </>
        ) : (
          <>
            <Sparkles size={16} />
            <span>Run Demo — 40 applications</span>
          </>
        )}
      </button>
      {err && (
        <p className="text-xs text-signal-red">
          {err}. Make sure the backend is running on :8000.
        </p>
      )}
    </div>
  );
}
