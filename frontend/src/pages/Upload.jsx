import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles } from "lucide-react";
import PillBadge from "../components/PillBadge";
import DropZone from "../components/DropZone";
import DemoModeButton from "../components/DemoModeButton";
import ApplicationCard from "../components/ApplicationCard";
import SkeletonCard from "../components/SkeletonCard";
import StatusToast from "../components/StatusToast";
import { useAnalysis } from "../hooks/useAnalysis";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { api } from "../lib/api";

export default function Upload() {
  const navigate = useNavigate();
  const {
    applicants,
    rings,
    total,
    analyzed,
    progress,
    isRunning,
    isComplete,
    batchComplete,
    wsStatus,
  } = useAnalysis();
  const [demoFiring, setDemoFiring] = useState(false);

  // D key — fires the seeded demo if the backend is reachable. We swallow
  // errors here too; DemoModeButton's own surface still shows the message
  // if the manual click path was taken.
  useKeyboardShortcuts({
    d: async () => {
      if (isRunning || demoFiring) return;
      setDemoFiring(true);
      try {
        await api.startDemo({ reset: true });
      } catch {
        /* user can still click the button; we don't pop a toast */
      } finally {
        setDemoFiring(false);
      }
    },
  });

  // Auto-route to results when the batch completes and at least one ring was
  // found. Small delay lets the toast register so the transition feels
  // intentional, not abrupt.
  useEffect(() => {
    if (!isComplete) return;
    const ringId = batchComplete?.rings?.[0]?.ring_id || rings[0]?.ring_id;
    const t = setTimeout(() => {
      navigate(ringId ? `/results/${ringId}` : "/results");
    }, 1200);
    return () => clearTimeout(t);
  }, [isComplete, batchComplete, rings, navigate]);

  const ringCount = batchComplete?.ring_count ?? rings.length;
  const pctDone = Math.round(progress * 100);
  // While the run is in flight but no event has landed yet, show 5 skeleton
  // rows so the panel isn't empty. Drop them as real events come in.
  const skeletonCount = Math.max(0, 5 - applicants.length);

  return (
    <section className="mx-auto max-w-6xl px-6 pt-14 pb-24">
      <div className="text-center">
        <PillBadge>Step 1 — analyse applications</PillBadge>
        <h1 className="mt-7 text-display-lg font-bold text-ink">
          Upload, or{" "}
          <span className="font-serif font-normal italic">run the demo</span>.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-base text-ink-muted md:text-lg">
          Drop a batch of loan-application PDFs to start a live analysis, or
          press Run Demo to use the seeded 40-applicant dataset.{" "}
          <span className="hidden md:inline">
            Press{" "}
            <kbd className="inline-flex items-center justify-center rounded border border-border-strong bg-cream-bg px-1.5 py-0.5 font-mono text-[0.7rem] text-ink">
              D
            </kbd>{" "}
            to fire the demo from anywhere.
          </span>
        </p>
      </div>

      <div className="mt-12 grid gap-6 md:grid-cols-[1.4fr_1fr]">
        <div className="flex flex-col gap-4">
          <DropZone disabled={isRunning} />
          <div className="card flex flex-col gap-3 p-6">
            <p className="text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
              Or run the seeded demo
            </p>
            <p className="text-sm leading-relaxed text-ink-muted">
              40 applications · 11 of them belong to the same fraud ring.
              Reuses existing demo data, or reset for a clean run.
            </p>
            <DemoModeButton />
            {demoFiring && (
              <p className="inline-flex items-center gap-2 text-xs text-ink-muted">
                <Sparkles size={12} className="text-ink" />
                Demo fired via keyboard shortcut…
              </p>
            )}
          </div>
        </div>

        {/* Live feed — skeletons until the first event lands, then a
            streaming list of ApplicationCard rows. */}
        <div className="card flex flex-col p-6">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="text-base font-semibold text-ink">Live feed</h2>
            <span className="text-xs text-ink-muted">
              {wsStatus === "open" ? "Connected" : `WS: ${wsStatus}`}
            </span>
          </div>

          {total > 0 && (
            <div className="mb-4">
              <div className="mb-1.5 flex items-center justify-between text-xs text-ink-muted">
                <span>
                  {analyzed} / {total} analysed
                </span>
                <span className="font-mono tabular-nums">{pctDone}%</span>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-cream-alt">
                <motion.div
                  className="h-full bg-ink"
                  initial={{ width: 0 }}
                  animate={{ width: `${pctDone}%` }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                />
              </div>
            </div>
          )}

          <div className="flex max-h-[440px] flex-col gap-2 overflow-y-auto pr-1">
            <AnimatePresence initial={false}>
              {applicants.length === 0 && !isRunning ? (
                <div className="rounded-card border border-dashed border-border-light bg-cream-alt/30 px-4 py-12 text-center text-sm text-ink-muted">
                  Waiting for events. Start the demo to populate this feed.
                </div>
              ) : (
                <>
                  {applicants
                    .slice()
                    .reverse()
                    .slice(0, 40)
                    .map((event, i) => (
                      <ApplicationCard
                        key={event.application_id || event._receivedAt || i}
                        event={event}
                        index={i}
                      />
                    ))}
                  {/* Skeleton rows fill the panel while the worker is warming */}
                  {isRunning &&
                    Array.from({ length: skeletonCount }).map((_, i) => (
                      <SkeletonCard key={`sk-${i}`} />
                    ))}
                </>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      <StatusToast
        wsStatus={wsStatus}
        analyzed={analyzed}
        total={total}
        isComplete={isComplete}
        ringCount={ringCount}
      />
    </section>
  );
}
