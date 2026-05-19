// Mock BATCH_COMPLETE payload — mirrors the shape the backend actually emits
// (see backend/workers/tasks.py :: _run_demo and _serialize_graph_for_frontend).
// Used during frontend development so the D3 reveal can be iterated on without
// spinning up the Postgres/Neo4j/Redis stack. Also used when the user hits
// /results?demo=mock for offline rehearsals.
//
// The ring members + edge density are calibrated to match what the real
// pipeline produces on the seeded 40-applicant dataset (≈700 edges, 1 ring of
// 11, 87.72% PHANTOM score → FREEZE_AND_ESCALATE).

const RING_NAMES = [
  "Rahul Sharma",
  "Rahul Sharrma",
  "Sandeep Patil",
  "Sandip Patil",
  "Ankit Verma",
  "Priya Singh",
  "Vikram Yadav",
  "Arjun Reddy",
  "Neha Gupta",
  "Manish Kumar",
  "Suresh Iyer",
];

const CLEAN_NAMES = [
  "Aarav Desai", "Ishita Bose", "Karan Mehta", "Sneha Kapoor", "Ravi Pillai",
  "Anita Joshi", "Rohan Naik", "Divya Rao", "Karthik Menon", "Pooja Shah",
  "Aditya Saxena", "Meera Krishnan", "Yash Agarwal", "Riya Bhattacharya",
  "Nikhil Chauhan", "Tanvi Malhotra", "Harsh Vardhan", "Sakshi Tripathi",
  "Aman Khurana", "Reema Sengupta", "Vivaan Banerjee", "Aditi Pandey",
  "Siddharth Nair", "Pranav Goswami", "Esha Roy", "Dev Kothari",
  "Avantika Sinha", "Rishi Mahajan", "Kavya Hegde",
];

const RING_CITY = ["Mumbai", "Pune", "Nagpur"];
const CLEAN_CITIES = ["Bangalore", "Chennai", "Hyderabad", "Delhi", "Ahmedabad", "Kolkata", "Jaipur", "Lucknow", "Indore", "Kochi"];

const RING_TOOL = "Canva 2.0";
const CLEAN_TOOLS = ["Finacle 7.3", "TCS BaNCS 9.1", "Oracle FLEXCUBE 12.4", "Temenos T24"];

const BASE_TIME = new Date("2025-08-14T10:32:00Z");

function pseudoUuid(seed) {
  // Deterministic short id — not a real UUID, just consistent across reloads.
  const hex = Math.abs(
    seed.split("").reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 0)
  ).toString(16);
  return `${hex.padStart(8, "0")}-mock-mock-mock-${seed.replace(/[^a-z0-9]/gi, "").slice(0, 8).padEnd(8, "0")}`;
}

function buildNodes() {
  const nodes = [];

  RING_NAMES.forEach((name, i) => {
    nodes.push({
      id: pseudoUuid(`ring-${i}-${name}`),
      name,
      city: RING_CITY[i % RING_CITY.length],
      amount: 5000000 + (i % 4) * 800000, // 50-80 lakh per member
      origin_tool: RING_TOOL,
      cbs_match_score: 0.36 + (i % 5) * 0.018, // 0.36 - 0.43 range
      submission_time: new Date(BASE_TIME.getTime() + i * 35 * 1000).toISOString(),
      in_ring: true,
    });
  });

  CLEAN_NAMES.forEach((name, i) => {
    nodes.push({
      id: pseudoUuid(`clean-${i}-${name}`),
      name,
      city: CLEAN_CITIES[i % CLEAN_CITIES.length],
      amount: 1500000 + ((i * 9301 + 49297) % 4500000),
      origin_tool: CLEAN_TOOLS[i % CLEAN_TOOLS.length],
      cbs_match_score: 0.82 + ((i * 17) % 16) / 100, // 0.82 - 0.97
      submission_time: new Date(
        BASE_TIME.getTime() + (1800 + i * 7200) * 1000
      ).toISOString(), // scattered across hours
      in_ring: false,
    });
  });

  return nodes;
}

function buildLinks(nodes) {
  const ring = nodes.filter((n) => n.in_ring);
  const clean = nodes.filter((n) => !n.in_ring);
  const links = [];

  // Heavy ring-internal links — every member shares the same template,
  // submission window, valuer, PII fragment, and "purpose" text. That's the
  // signal Louvain locks onto.
  for (let i = 0; i < ring.length; i++) {
    for (let j = i + 1; j < ring.length; j++) {
      const a = ring[i].id;
      const b = ring[j].id;
      links.push({ source: a, target: b, type: "TEMPLATE_MATCH", weight: 1.0 });
      links.push({ source: a, target: b, type: "TIMING_PROXIMITY", weight: 0.4 });
      links.push({ source: a, target: b, type: "SAME_VALUER", weight: 0.7 });
      if (j - i <= 4) {
        links.push({ source: a, target: b, type: "TEXT_MATCH", weight: 0.8 });
      }
      if (j - i <= 2) {
        links.push({ source: a, target: b, type: "SHARED_PII", weight: 0.6 });
      }
    }
  }
  // Two name-similarity pairs: Rahul Sharma / Sharrma, Sandeep / Sandip
  links.push({ source: ring[0].id, target: ring[1].id, type: "NAME_SIMILARITY", weight: 0.5 });
  links.push({ source: ring[2].id, target: ring[3].id, type: "NAME_SIMILARITY", weight: 0.5 });

  // Sparse innocuous links among clean applicants — sharing one weak signal
  // (timing, common valuer) is realistic but doesn't cross any threshold.
  let seed = 7;
  const rng = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
  for (let n = 0; n < 60; n++) {
    const i = Math.floor(rng() * clean.length);
    let j = Math.floor(rng() * clean.length);
    if (i === j) j = (j + 1) % clean.length;
    const types = ["TIMING_PROXIMITY", "SAME_VALUER", "SAME_GUARANTOR"];
    const type = types[Math.floor(rng() * types.length)];
    links.push({
      source: clean[i].id,
      target: clean[j].id,
      type,
      weight: 0.3 + rng() * 0.3,
    });
  }
  // A handful of "bridges" between one ring member and one clean (noise — the
  // graph isn't perfectly partitioned in real life).
  for (let k = 0; k < 6; k++) {
    links.push({
      source: ring[k % ring.length].id,
      target: clean[(k * 5) % clean.length].id,
      type: "TIMING_PROXIMITY",
      weight: 0.3,
    });
  }
  return links;
}

function buildRing(nodes) {
  const ringNodes = nodes.filter((n) => n.in_ring);
  const ringId = "RING-B4BAF28963BB";
  const members = ringNodes.map((n) => ({
    application_id: n.id,
    applicant_name: n.name,
    name: n.name,
    city: n.city,
    loan_amount_inr: n.amount,
    submission_time: n.submission_time,
    cbs_match_score: n.cbs_match_score,
    origin_tool: n.origin_tool,
    font_subset_hash: "9c1f3d8e4b5a2710c6f4e8b9a3d2f1e0",
  }));
  const totalExposure = members.reduce((s, m) => s + m.loan_amount_inr, 0);
  return {
    ring_id: ringId,
    ring_size: members.length,
    total_exposure_inr: totalExposure,
    phantom_confidence_pct: 87.72,
    phantom_score: 0.8772,
    behavioral_score: 0.9145,
    origin_match_score: 0.8398,
    recommended_action: "FREEZE_AND_ESCALATE",
    members,
    origin_summary:
      "All 11 members produced documents with Canva 2.0 as the PDF producer — flagged as a consumer design tool, not a Core Banking System. Mean CBS-match score across the cluster is 0.39, versus 0.91 for the rest of the batch.",
    timing_summary:
      "Submissions clustered in a 6-minute window starting 2025-08-14T10:32:00Z. The expected inter-arrival gap for unrelated applications in this dataset is ~2 hours.",
    narrative:
      "Cross-signal analysis identifies a coordinated cluster of 11 applicants sharing a verbatim 'small business expansion' loan purpose, the same property valuer (Anand Property Services), a common phone prefix (+91 98765), and the same Canva-generated document template. Two pairs of names are near-duplicates indicative of identity overlap. Aggregate exposure is ₹6.23 crore. Recommended action: freeze disbursement and escalate to the fraud investigation desk.",
    evidence_hash_sha256:
      "044b2e1f9a8d6c5b3e7f1a2d4c8b6e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d",
    evidence_signature_ed25519:
      "MEUCIQDLZk3xQYWmZ8HrJ4w5cP2hKb9YXfV2NwQ6dGmKlT3p4QIgPmH8nFvK1xZjY7Wb3sR5DvT9LqMpA2bC4eFn0kI8sJM=",
    signing_key_id: "11b80e056b5eae5f",
  };
}

const nodes = buildNodes();
const links = buildLinks(nodes);
const ring = buildRing(nodes);

export const mockBatchComplete = {
  type: "BATCH_COMPLETE",
  batch_id: "BATCH-MOCK-DEMO-RUN",
  ring_count: 1,
  rings: [ring],
  graph_data: { nodes, links },
};

export const mockRing = ring;
export const mockGraph = { nodes, links };
