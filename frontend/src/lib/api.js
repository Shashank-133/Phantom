// Minimal fetch wrapper. All paths go through Vite's /api proxy in dev and
// are same-origin in prod (frontend served by Caddy/nginx in front of FastAPI).
const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const api = {
  // Demo mode — kicks off the seeded 40-applicant pipeline.
  startDemo: ({ reset = false } = {}) =>
    request(`/analyze/demo${reset ? "?reset=true" : ""}`, { method: "POST" }),

  // Result fetchers (used to hydrate the page if the user lands on /results
  // directly without watching the live WebSocket stream).
  listRings: () => request("/results/rings"),
  getRing: (ringId) => request(`/results/rings/${ringId}`),

  // Evidence bundle (signed JSON). URL the user can download directly.
  evidenceUrl: (ringId) => `${BASE}/evidence/${ringId}`,
  evidencePdfUrl: (ringId) => `${BASE}/evidence/${ringId}.pdf`,
  publicKeyUrl: () => `${BASE}/evidence/public-key`,

  // Health/status — used by Layout to show a live dot.
  health: () => request("/health"),
};
