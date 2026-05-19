import { useMemo } from "react";
import { useWebSocket } from "./useWebSocket";

// Folds the raw event stream from useWebSocket into a tidy shape the UI can
// render against. Selects the "interesting" pieces — current progress, the
// graph snapshot, the per-applicant list, the detected rings, the batch
// summary — so pages don't each have to repeat the same reducers.
export function useAnalysis() {
  const { events, lastEvent, status, clear } = useWebSocket("/ws");

  const state = useMemo(() => {
    let batch = null;
    let total = 0;
    let analyzed = 0;
    const applicants = new Map(); // id → latest DOCUMENT_ANALYZED payload
    const rings = new Map(); // ring_id → latest RING_DETECTED payload
    let graph = null;
    let communities = null;
    let batchComplete = null;

    for (const ev of events) {
      switch (ev.type) {
        case "ANALYSIS_STARTED":
          batch = ev.batch_id;
          total = ev.total ?? 0;
          analyzed = 0;
          break;
        case "DOCUMENT_ANALYZED": {
          analyzed += 1;
          const key =
            ev.application_id || ev.id || `${ev.applicant_name}-${analyzed}`;
          applicants.set(key, ev);
          break;
        }
        case "GRAPH_BUILT":
          graph = ev;
          break;
        case "COMMUNITIES_DETECTED":
          communities = ev;
          break;
        case "RING_DETECTED":
          rings.set(ev.ring_id, ev);
          break;
        case "BATCH_COMPLETE":
          batchComplete = ev;
          break;
        default:
          break;
      }
    }

    return {
      batch,
      total,
      analyzed,
      progress: total > 0 ? analyzed / total : 0,
      applicants: Array.from(applicants.values()),
      rings: Array.from(rings.values()),
      graph,
      communities,
      batchComplete,
      isRunning: total > 0 && analyzed < total,
      isComplete: !!batchComplete,
    };
  }, [events]);

  return { ...state, lastEvent, wsStatus: status, clear };
}
