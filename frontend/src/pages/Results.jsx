import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Loader2, Sparkles } from "lucide-react";
import PillBadge from "../components/PillBadge";
import StatusToast from "../components/StatusToast";
import FraudGraph from "../components/FraudGraph";
import PhantomReport from "../components/PhantomReport";
import OriginTree from "../components/OriginTree";
import { useAnalysis } from "../hooks/useAnalysis";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { api } from "../lib/api";
import { mockBatchComplete } from "../data/demo_dataset";

export default function Results() {
  const { ringId } = useParams();
  const [searchParams] = useSearchParams();
  const useMock = searchParams.get("demo") === "mock";

  const {
    rings: liveRings,
    batchComplete: liveBatch,
    graph: liveGraph,
    analyzed,
    total,
    isComplete,
    wsStatus,
  } = useAnalysis();

  const [fallbackRing, setFallbackRing] = useState(null);
  const [loadingFallback, setLoadingFallback] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const fraudGraphRef = useRef(null);

  // Source-of-truth merge: mock mode wins outright; otherwise live WS state;
  // otherwise an API-hydrated single ring (for direct-link arrivals).
  const rings = useMock ? mockBatchComplete.rings : liveRings;
  const batchComplete = useMock ? mockBatchComplete : liveBatch;

  const ring = useMemo(() => {
    if (ringId) return rings.find((r) => r.ring_id === ringId) || fallbackRing;
    return rings[0] || fallbackRing;
  }, [rings, ringId, fallbackRing]);

  // Graph payload — prefer the BATCH_COMPLETE attachment, fall back to the
  // GRAPH_BUILT event from the WS feed.
  const graphData = useMock
    ? mockBatchComplete.graph_data
    : batchComplete?.graph_data || liveGraph?.graph_data || null;

  // Direct-link fallback
  useEffect(() => {
    if (useMock || liveRings.find((r) => r.ring_id === ringId)) return;
    if (!ringId || fallbackRing || loadingFallback) return;
    let cancelled = false;
    setLoadingFallback(true);
    api
      .getRing(ringId)
      .then((data) => {
        if (!cancelled) setFallbackRing(data);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingFallback(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ringId, liveRings, fallbackRing, loadingFallback, useMock]);

  // Keyboard shortcuts. Esc has dual duty: prefer closing the drawer if open,
  // else do nothing — Layout's Escape binding handles the help modal.
  useKeyboardShortcuts({
    Escape: () => {
      if (selectedNode) setSelectedNode(null);
    },
    r: () => fraudGraphRef.current?.replay(),
  });

  // Empty state
  if (!ring || !graphData) {
    return (
      <section className="mx-auto max-w-3xl px-6 py-24 text-center">
        <PillBadge>Results</PillBadge>
        <h1 className="mt-7 text-display-md font-bold text-ink">
          Nothing analysed{" "}
          <span className="font-serif font-normal italic">yet</span>.
        </h1>
        <p className="mx-auto mt-6 max-w-md text-ink-muted">
          {loadingFallback
            ? "Loading the ring report…"
            : "Run the demo or upload a batch first."}
        </p>
        {loadingFallback && (
          <Loader2
            size={20}
            className="mx-auto mt-6 animate-spin text-ink-muted"
          />
        )}
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Link to="/upload" className="btn-primary">
            <ArrowLeft size={16} /> Go to analyse
          </Link>
          <Link to="/results?demo=mock" className="btn-secondary">
            <Sparkles size={16} /> Preview with mock data
          </Link>
        </div>
        <StatusToast
          wsStatus={wsStatus}
          analyzed={analyzed}
          total={total}
          isComplete={isComplete}
          ringCount={rings.length}
        />
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-7xl px-6 py-12">
      {/* Slim header — the big stat strip moved into PhantomReport, so this
          page is dominated by the graph as it should be. */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <PillBadge>
            {useMock ? "Mock demo · offline preview" : "Live results"}
          </PillBadge>
          <h1 className="mt-5 text-display-md font-bold text-ink">
            Ring detected ·{" "}
            <span className="font-serif font-normal italic">
              the network speaks
            </span>
            .
          </h1>
        </div>
        <div className="text-right text-xs text-ink-muted">
          <p>
            {graphData.nodes.length} applicants · {graphData.links.length} edges
          </p>
          {!useMock && (
            <p className="mt-0.5 font-mono">
              {wsStatus === "open" ? "WebSocket connected" : `WS: ${wsStatus}`}
            </p>
          )}
        </div>
      </div>

      {/* Graph + Report — graph is the loudest element on the page */}
      <motion.div layout className="grid gap-6 lg:grid-cols-[1.55fr_1fr]">
        <div className="card relative overflow-hidden">
          <div className="border-b border-border-light px-5 py-3.5 text-xs text-ink-muted">
            Cream canvas · gray dots · click any node for the origin tree ·
            press{" "}
            <kbd className="inline-flex items-center justify-center rounded border border-border-strong bg-cream-bg px-1.5 py-0.5 font-mono text-[0.65rem] text-ink">
              R
            </kbd>{" "}
            to replay the cinematic
          </div>
          <FraudGraph
            ref={fraudGraphRef}
            data={graphData}
            onNodeClick={setSelectedNode}
            autoReveal
            height={560}
          />
        </div>

        <PhantomReport ring={ring} />
      </motion.div>

      <OriginTree node={selectedNode} onClose={() => setSelectedNode(null)} />

      <StatusToast
        wsStatus={wsStatus}
        analyzed={analyzed}
        total={total}
        isComplete={isComplete}
        ringCount={rings.length}
      />
    </section>
  );
}
