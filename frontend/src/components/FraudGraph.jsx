import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import * as d3 from "d3";
import { Play, RotateCcw, Volume2, VolumeX } from "lucide-react";
import { colors } from "../theme/colors";
import { usePrefersReducedMotion } from "../hooks/useKeyboardShortcuts";

// The cinematic reveal — Day 7's money moment.
//
// 1) On mount, 40 gray nodes settle into a force-directed layout on a cream
//    background. Edges are barely visible (light, low opacity).
// 2) When `play` is triggered (button or auto when `autoReveal`), the
//    non-ring 29 nodes fade to a dimmer cream. The 11 ring members scale up
//    with a 60ms stagger and transition from gray to signal-red, with a
//    Gaussian-blur glow filter behind them.
// 3) Ring-internal edges light up red afterwards.
// 4) An optional Web Audio "ping" tone fires once at the reveal — judges
//    remember sound. Off by default; user opts in via the speaker toggle.
//
// Click any node → fire `onNodeClick(node)` so the parent can open the
// OriginTree forensic drill-down.

const RING_FILL = colors.signal.red;
const RING_STROKE = "#7a1f12";
const BASE_NODE = colors.ink.placeholder; // gray before reveal
const DIMMED_NODE = colors.cream.dim;     // non-ring after reveal
const NEUTRAL_LINK = "#C9C0AE";           // very subtle pre-reveal
const RING_LINK = colors.signal.red;

function playPing(enabled) {
  if (!enabled || typeof window === "undefined" || !window.AudioContext) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.45);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.04);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.7);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.75);
  } catch {
    /* audio blocked — silently no-op */
  }
}

const FraudGraph = forwardRef(function FraudGraph(
  { data, onNodeClick, autoReveal = false, height = 520 },
  ref
) {
  const wrapRef = useRef(null);
  const svgRef = useRef(null);
  const simRef = useRef(null);
  const [revealed, setRevealed] = useState(false);
  const [audioOn, setAudioOn] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  // Smaller on phones so portrait orientation isn't a vertical scroll-fest.
  const responsiveHeight =
    typeof window !== "undefined" && window.innerWidth < 640
      ? Math.min(height, 380)
      : height;

  // Build the simulation + draw once per data change.
  useEffect(() => {
    if (!data || !data.nodes || !data.links) return;

    const wrap = wrapRef.current;
    const width = wrap.clientWidth;
    const h = responsiveHeight;

    // Deep-copy nodes/links so D3's mutations don't leak into the parent's
    // immutable state. Resolve link source/target by id strings.
    const nodes = data.nodes.map((d) => ({ ...d }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = data.links
      .map((l) => ({
        ...l,
        source: typeof l.source === "string" ? byId.get(l.source) : l.source,
        target: typeof l.target === "string" ? byId.get(l.target) : l.target,
      }))
      .filter((l) => l.source && l.target);

    const svg = d3
      .select(svgRef.current)
      .attr("viewBox", `0 0 ${width} ${h}`)
      .attr("width", "100%")
      .attr("height", h);

    svg.selectAll("*").remove();

    // Defs: glow filter for ring nodes during reveal
    const defs = svg.append("defs");
    const filter = defs
      .append("filter")
      .attr("id", "ring-glow")
      .attr("x", "-50%")
      .attr("y", "-50%")
      .attr("width", "200%")
      .attr("height", "200%");
    filter
      .append("feGaussianBlur")
      .attr("stdDeviation", "4")
      .attr("result", "blur");
    const merge = filter.append("feMerge");
    merge.append("feMergeNode").attr("in", "blur");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    // Link layer first so circles render on top.
    const linkSel = svg
      .append("g")
      .attr("class", "links")
      .attr("stroke", NEUTRAL_LINK)
      .attr("stroke-opacity", 0.35)
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("class", (d) => {
        const ringLink = d.source.in_ring && d.target.in_ring;
        return `link ${ringLink ? "ring-link" : ""}`;
      })
      .attr("stroke-width", (d) => 0.6 + (d.weight || 0.5) * 0.6);

    const nodeSel = svg
      .append("g")
      .attr("class", "nodes")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("class", (d) => `node ${d.in_ring ? "ring-node" : ""}`)
      .attr("r", 7)
      .attr("fill", BASE_NODE)
      .attr("stroke", "#1A1A1A")
      .attr("stroke-opacity", 0.0)
      .attr("stroke-width", 1.4)
      .attr("cursor", "pointer")
      .on("click", (event, d) => onNodeClick?.(d))
      .on("mouseover", function (_event, d) {
        d3.select(this)
          .transition()
          .duration(120)
          .attr("stroke-opacity", 0.8);
        labelSel
          .filter((n) => n.id === d.id)
          .transition()
          .duration(120)
          .attr("opacity", 1);
      })
      .on("mouseout", function (_event, d) {
        d3.select(this)
          .transition()
          .duration(180)
          .attr("stroke-opacity", 0.0);
        labelSel
          .filter((n) => n.id === d.id)
          .transition()
          .duration(180)
          .attr("opacity", (n) => (n.in_ring && revealed ? 0.9 : 0));
      })
      .call(
        d3
          .drag()
          .on("start", (event, d) => {
            if (!event.active) simRef.current.alphaTarget(0.25).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simRef.current.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    // Labels — appear on hover, plus auto-show for ring members post-reveal.
    const labelSel = svg
      .append("g")
      .attr("class", "labels")
      .attr("pointer-events", "none")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .text((d) => d.name || "")
      .attr("font-size", 10)
      .attr("font-family", "Inter, sans-serif")
      .attr("fill", colors.ink.DEFAULT)
      .attr("text-anchor", "middle")
      .attr("dy", -12)
      .attr("opacity", 0);

    const sim = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d) => d.id)
          .distance((d) =>
            d.source.in_ring && d.target.in_ring ? 60 : 110
          )
          .strength((d) => (d.source.in_ring && d.target.in_ring ? 0.7 : 0.15))
      )
      .force("charge", d3.forceManyBody().strength(-160))
      .force("collide", d3.forceCollide(14))
      .force("center", d3.forceCenter(width / 2, h / 2))
      .alpha(1)
      .on("tick", () => {
        linkSel
          .attr("x1", (d) => d.source.x)
          .attr("y1", (d) => d.source.y)
          .attr("x2", (d) => d.target.x)
          .attr("y2", (d) => d.target.y);
        nodeSel.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
        labelSel.attr("x", (d) => d.x).attr("y", (d) => d.y);
      });

    simRef.current = sim;

    return () => {
      sim.stop();
    };
  }, [data, responsiveHeight, onNodeClick, revealed]);

  // Reveal effect — runs the choreography. Re-runs if `revealed` flips back
  // to true after a reset.
  useEffect(() => {
    if (!revealed) return;
    const svg = d3.select(svgRef.current);
    if (svg.empty()) return;

    // Phase 1 — dim the chorus
    svg
      .selectAll("circle.node:not(.ring-node)")
      .transition()
      .duration(600)
      .ease(d3.easeCubicInOut)
      .attr("fill", DIMMED_NODE);

    svg
      .selectAll("line.link:not(.ring-link)")
      .transition()
      .duration(600)
      .attr("stroke-opacity", 0.12);

    // Phase 2 — ring nodes pulse to red with stagger. Reduced-motion users
    // get the same end state, just without the bounce overshoot or stagger.
    const ringNodes = svg.selectAll("circle.ring-node");
    const ringTransition = ringNodes
      .transition()
      .delay((_d, i) => (reducedMotion ? 0 : 350 + i * 60))
      .duration(reducedMotion ? 200 : 450)
      .ease(reducedMotion ? d3.easeCubicOut : d3.easeBackOut.overshoot(2));
    ringTransition
      .attr("r", 12)
      .attr("fill", RING_FILL)
      .attr("stroke", RING_STROKE)
      .attr("stroke-opacity", 0.9)
      .attr("filter", "url(#ring-glow)");

    // Phase 3 — ring edges light up
    svg
      .selectAll("line.ring-link")
      .transition()
      .delay(700)
      .duration(700)
      .attr("stroke", RING_LINK)
      .attr("stroke-opacity", 0.55)
      .attr("stroke-width", 1.6);

    // Phase 4 — labels for ring members fade in
    svg
      .selectAll("text")
      .filter((d) => d.in_ring)
      .transition()
      .delay(1100)
      .duration(500)
      .attr("opacity", 0.92);

    // Audio cue lands with phase 2
    setTimeout(() => playPing(audioOn), 350);
  }, [revealed, audioOn, reducedMotion]);

  const reset = () => {
    setRevealed(false);
    const svg = d3.select(svgRef.current);
    svg.selectAll("circle.node").attr("filter", null);
    svg
      .selectAll("circle.node:not(.ring-node)")
      .interrupt()
      .attr("fill", BASE_NODE);
    svg
      .selectAll("circle.ring-node")
      .interrupt()
      .attr("r", 7)
      .attr("fill", BASE_NODE)
      .attr("stroke-opacity", 0.0)
      .attr("filter", null);
    svg
      .selectAll("line.link")
      .interrupt()
      .attr("stroke", NEUTRAL_LINK)
      .attr("stroke-opacity", 0.35)
      .attr("stroke-width", (d) => 0.6 + (d.weight || 0.5) * 0.6);
    svg.selectAll("text").interrupt().attr("opacity", 0);
  };

  // Auto-reveal when the parent says the batch just completed.
  useEffect(() => {
    if (autoReveal && !revealed) {
      const t = setTimeout(() => setRevealed(true), reducedMotion ? 200 : 700);
      return () => clearTimeout(t);
    }
  }, [autoReveal, revealed, reducedMotion]);

  // Imperative handle for parents — lets keyboard shortcuts trigger Replay
  // without lifting the revealed state up.
  useImperativeHandle(
    ref,
    () => ({
      replay() {
        reset();
        requestAnimationFrame(() => setRevealed(true));
      },
      reset,
    }),
    [] // reset is stable for our purposes
  );

  return (
    <div ref={wrapRef} className="relative w-full">
      <svg
        ref={svgRef}
        className="block w-full touch-none"
        role="img"
        aria-label="Cross-applicant fraud graph"
      />

      {/* Floating controls — bottom-right, lift on hover */}
      <div className="absolute bottom-3 right-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setAudioOn((v) => !v)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border-strong bg-cream-bg/95 text-ink-muted transition-colors hover:bg-cream-alt focus:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-cream-bg"
          aria-label={audioOn ? "Mute reveal sound" : "Enable reveal sound"}
        >
          {audioOn ? <Volume2 size={14} /> : <VolumeX size={14} />}
        </button>
        {revealed ? (
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-2 rounded-full border border-border-strong bg-cream-bg/95 px-3.5 py-2 text-xs font-medium text-ink transition-colors hover:bg-cream-alt focus:outline-none focus-visible:ring-2 focus-visible:ring-ink"
          >
            <RotateCcw size={13} />
            Replay
            <kbd className="ml-1 hidden font-mono text-[0.65rem] text-ink-muted sm:inline">
              R
            </kbd>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setRevealed(true)}
            className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-xs font-medium text-cream-bg transition-colors hover:bg-ink/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-cream-bg"
          >
            <Play size={13} />
            Reveal the ring
          </button>
        )}
      </div>
    </div>
  );
});

export default FraudGraph;
