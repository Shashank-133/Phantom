# PHANTOM — Master Analysis & Build Plan

> **Project**: PHANTOM — Fraud Ring & Document Origin Intelligence Platform
> **Event**: SuRaksha Cyber Hackathon 2.0 (Canara Bank)
> **Goal**: Hackathon-winning + startup-ready
> **Document purpose**: One source of truth. Read this before writing any code.

---

## Table of Contents

1. [Verdict on the 8 "bugs" from Prompt #2](#1-verdict-on-the-8-bugs-from-prompt-2)
2. [Additional issues neither prompt caught](#2-additional-issues-neither-prompt-caught)
3. [Grok / Free-tier LLM strategy](#3-grok--free-tier-llm-strategy)
4. [Free-tier service stack (final)](#4-free-tier-service-stack-final)
5. [Scope reality check — what's hackathon, what's startup](#5-scope-reality-check)
6. [Final tech stack — what to keep, cut, swap](#6-final-tech-stack)
7. [Architecture & data flow](#7-architecture--data-flow)
8. [Design system — the "coldiq cream" theme](#8-design-system--the-coldiq-cream-theme)
9. [Phased build plan (Day by Day)](#9-phased-build-plan)
10. [Risk register](#10-risk-register)
11. [Accounts & one-time setup checklist](#11-accounts--one-time-setup-checklist)
12. [What this project WILL be — in simple English](#12-what-this-project-will-be--in-simple-english)
13. [What this project will NOT be — in simple English](#13-what-this-project-will-not-be)

---

## 1. Verdict on the 8 "bugs" from Prompt #2

Each bug from Prompt #2 was real or not. Honest grading:

### Bug 1 — Socket.io vs Native WebSocket mismatch → ✅ **REAL & CRITICAL**
Socket.io has its own handshake layer on top of WebSocket. A FastAPI `@app.websocket("/ws")` endpoint speaks raw WebSocket — a `socket.io-client` will hit it, fail the handshake, and the connection silently never works. The "fix" (native WebSocket on both sides) is correct. **Do this.**

### Bug 2 — ViT as classifier vs feature extractor → ✅ **REAL**
ViT's classification head outputs 1000 ImageNet logits ("dog", "cat", etc.) — useless for "is this a CBS document?" The CLS token from the last hidden state (768-dim) is the right embedding. The fix is correct.
**But a deeper concern Prompt #2 missed**: there is no "real CBS document corpus" to compute a centroid against. So ViT cosine-distance-to-centroid is partly theatrical. **My recommendation**: keep ViT, but instead of comparing to a "CBS centroid," use it for **pairwise similarity within the uploaded batch** — that's where the real signal lives (11 fake docs will cluster tightly in embedding space).

### Bug 3 — Sentence-transformers model not specified → ⚠️ **REAL but LOW IMPACT**
Yes, `all-MiniLM-L6-v2` is the right pick (90 MB, fast, 384-dim). But honestly: for 40 docs, text similarity does almost no fraud-detection work. The signal lives in **metadata + timing + font hash**. Treat sentence-transformers as nice-to-have, not load-bearing.

### Bug 4 — generate_demo.py must set producer metadata explicitly → ✅ **REAL & CRITICAL**
The whole demo collapses if the 11 "Canva" PDFs don't actually carry a `Canva` producer string. **But Prompt #2's fix is incomplete**: ReportLab writes its own producer string (`"ReportLab"`). You can't ask ReportLab to lie about being Canva. **The real fix**: generate the PDF with ReportLab, then post-process with `pikepdf` or `pypdf` to overwrite the `/Producer` and `/Creator` metadata fields. Two extra lines, but missing them breaks the demo.

### Bug 5 — GraphSAGE has no training data → ✅ **REAL**
You cannot train a GNN on 40 nodes. Prompt #2's compromise ("stretch goal, passthrough if untrained") is OK but **my stronger recommendation: drop GraphSAGE entirely**. Louvain + the rule-based cross-signal score reaches 97% confidence on the demo deterministically. GraphSAGE adds a 1 GB+ PyTorch Geometric install, Windows install pain, and zero demo value. **Cut it.**

### Bug 6 — Pre-download models, don't fetch at container start → ✅ **REAL & CRITICAL**
HuggingFace downloads ~450 MB on first model load. Hackathon WiFi will choke. Prompt #2's `download_models.py` + cache volume is correct. **Do this.**

### Bug 7 — Cross-signal formula was undefined → ✅ **REAL**
Original prompt left scoring abstract. Prompt #2 defined precise weights. Correct fix. **Use exactly the formula in Prompt #2.**

### Bug 8 — No DB seeding instructions → ✅ **REAL**
Spec said "pre-seed" without saying how. Prompt #2's `init_demo_data()` in FastAPI lifespan is the right pattern. **Do this.**

### Overall grade on Prompt #2's analysis
**7.5 out of 8 bugs are real and well-fixed**. Bug 3 is technically real but trivially impactful. Prompt #2 is a serious, competent revision — not timepass. **Use it as the baseline spec.**

---

## 2. Additional issues neither prompt caught

These will bite us. Listed by severity.

### 🔴 A. ReportLab cannot fake the producer string by itself
Prompt #2's fix says "set producer to 'Canva 2.0'" but ReportLab sets its own producer. **Solution**: after ReportLab generates each PDF, run:
```python
import pikepdf
with pikepdf.open(path, allow_overwriting_input=True) as pdf:
    with pdf.open_metadata() as meta:
        meta['xmp:CreatorTool'] = 'Canva'
    pdf.docinfo['/Producer'] = 'Canva 2.0'
    pdf.docinfo['/Creator'] = 'Canva'
    pdf.save(path)
```

### 🔴 B. "Cryptographically signed" SHA-256 is not actually a signature
A hash ≠ a signature. A judge with a security background will flag this immediately. **Fix**: add real Ed25519 signing — 8 lines with the `cryptography` library. Generate keypair on first startup, store private key in a Docker volume, expose public key via an endpoint, sign evidence bundles with the private key. This is the difference between "looks like a startup" and "is a startup."

### 🔴 C. Windows + Docker Desktop + 6-service stack = pain
The user is on Windows 11. The stack (Postgres + Neo4j + Redis + Backend + Celery + Frontend) will consume 6–8 GB RAM minimum, plus WSL2 overhead. **Mitigation**: run heavy infra (Postgres, Neo4j, Redis) in Docker, but run FastAPI/Celery/frontend natively on host during development with hot reload. Only spin everything up via Docker Compose for the final demo.

### 🟡 D. PyTorch Geometric is install-hell on Windows
Tied to Bug 5. Confirms: **drop GraphSAGE entirely**. PyG needs matching CUDA/torch versions and often fails on Windows. We don't need it.

### 🟡 E. No PHANTOM Report PDF export
Spec returns a JSON. For court-ready feel, the "Download Evidence Bundle" button should produce a real PDF. **Fix**: generate a polished PDF with ReportLab (or WeasyPrint for HTML→PDF, which gives nicer typography).

### 🟡 F. Demo Mode without seeded DB = crash
If Demo Mode is clicked before lifespan seeding finishes, it'll fail. **Fix**: Demo Mode endpoint always seeds-if-empty first, idempotently.

### 🟡 G. D3 animation strategy is hand-wavy
"Animate to red over 800ms" isn't enough. **Concrete pattern**: use D3's `transition().duration(800).ease(d3.easeCubicInOut)` on `.attr("fill", ...)`. For the glow effect, use SVG `<filter>` with `feGaussianBlur` and animate its `stdDeviation`. For the pulse, use `animateTransform` on a sibling circle.

### 🟡 H. No tests, no CI
For startup-level credibility, at minimum: pytest smoke tests on `cross_signal_engine.calculate_phantom_score()` and `origin_engine.score_document()` with synthetic inputs. 30 minutes of work.

### 🟢 I. No README / architecture diagram / pitch
For startup pitching: 1-page README with the hero pitch, 1 system diagram (mermaid is fine), 1 demo GIF. Hackathon judges grade on this too.

### 🟢 J. Indian names dataset
Prompt #2 suggests `randomuser.me/api/?nat=in&results=40`. Fine, but better: pre-bake the 40 names into `demo_data/generate_demo.py` so the demo has zero internet dependency at runtime.

### 🟢 K. No observability
Not needed for hackathon. For startup level: add `loguru` for structured logging and a `/health` endpoint with DB ping. Free, 10 minutes.

---

## 3. Grok / Free-tier LLM strategy

### Is Grok / xAI usable for free?
**Mostly yes, with caveats.** xAI (console.x.ai) does offer free credits to new users for evaluating their API. The exact amount/duration of the "$25 every month" claim from Prompt #2 has changed over time — at minimum, new accounts get evaluation credits sufficient for a hackathon. The API is OpenAI-compatible (drop-in client swap).

### But you don't need an LLM for the core demo
Every score, every flag, every graph edge is computed by deterministic Python. The only place an LLM helps is the **narrative paragraph** in the PHANTOM Report:
> "Our analysis identified a coordinated fraud ring of 11 applicants operating across Mumbai, Pune, and Nagpur..."

### Recommended LLM strategy (in order of preference)
| Option | Free? | Reliability | Recommendation |
|---|---|---|---|
| **f-string template** | Yes (no API) | 100% | **Default. Use this.** |
| **Google Gemini 1.5 Flash** | 15 RPM free, no credit card | Very high | Best free LLM option if you want LLM-generated narrative |
| **Groq** (NOT Grok) | Generous free tier, ~30 RPM | High | Excellent speed, free LLM inference |
| **xAI Grok** | Free credits on signup | High | Good fallback |
| OpenAI / Anthropic API | Paid | High | **Avoid for this project** |

**My strong recommendation**: ship with f-string templates. Add Gemini Flash as a progressive enhancement — if API key is set in `.env`, use it; otherwise fall back to template. **The LLM is not allowed to be a dependency. Demo cannot fail because of network.**

### Free LLM accounts to create
1. **Google AI Studio** (aistudio.google.com) — Gemini API key, instant, no credit card, 15 RPM Flash free tier
2. **Groq** (console.groq.com) — Llama 3.1 70B and Mixtral free, very fast
3. **xAI Grok** (console.x.ai) — backup option, $25 evaluation credits

---

## 4. Free-tier service stack (final)

### Things that run locally in Docker (100% free, no account)
- PostgreSQL 15
- Neo4j 5 Community
- Redis 7
- FastAPI backend
- Celery worker
- React frontend (Vite dev server)
- All Python ML libs (PyMuPDF, scipy, ImageHash, sentence-transformers, FAISS)

### Hosted services (free tier, account required)
| Service | Use | Free tier | Catch |
|---|---|---|---|
| **GitHub** | Code repo | Unlimited public/private repos | None |
| **Render.com** | Optional deploy | 512 MB RAM, cold starts after 15min | Cold start kills demo flow |
| **Railway.app** | Optional deploy | $5 monthly credit | Card required for verification |
| **ngrok** | Tunnel for remote judges | 1 random URL, free | URL changes per restart |
| **Google AI Studio** | Gemini Flash for narrative | 15 RPM free | Internet required |
| **Cloudflare Tunnel** | Better than ngrok if needed | Free with named tunnel | Slight setup overhead |

### Hard rule
**The demo runs from `docker-compose up` on the laptop. Hosted services are bonus/judge-access only. WiFi failure on stage is survivable.**

### Services to avoid (cost money or risky)
- OpenAI / Anthropic paid APIs
- Pinecone (use FAISS)
- Neo4j AuraDB (use Community in Docker)
- AWS / GCP / Azure
- HuggingFace Inference API (download locally)

---

## 5. Scope reality check

### Honest time budget (1 person, focused)
| Slice | Time |
|---|---|
| Backend pipeline (pdf_parser → origin_engine → cross_signal) | 1.5 days |
| Neo4j + graph builder + Louvain | 0.5 day |
| Celery + WebSockets + API routes | 0.5 day |
| Docker Compose + healthchecks + seeding | 0.5 day |
| `generate_demo.py` with proper metadata injection | 0.5 day |
| Frontend: layout, upload, results page | 1 day |
| Frontend: D3 fraud graph with cinematic reveal | 1 day |
| Frontend: PHANTOM Report panel + theme polish | 1 day |
| Integration, smoke tests, demo rehearsal | 1 day |
| **MVP total** | **7.5 days** |
| Polish (PDF export, Ed25519, narrative LLM, theme refinement) | 2 days |
| README + architecture diagram + demo video | 1 day |
| **Startup-ready total** | **~10.5 days** |

### Phased delivery
- **Phase 1 (MVP)** = "demo works flawlessly" → days 1–7
- **Phase 2 (Polish)** = "judges think this is a startup" → days 8–9
- **Phase 3 (Pitch)** = "deployable + documented" → days 10+

---

## 6. Final tech stack

### KEEP
- React + Vite + TailwindCSS + Framer Motion + D3.js
- **Native WebSocket** (no Socket.io)
- FastAPI + Celery + Redis
- PyMuPDF + pikepdf (added) + scipy + ImageHash + ReportLab
- HuggingFace ViT-base-patch16-224 (as feature extractor)
- `sentence-transformers/all-MiniLM-L6-v2`
- python-louvain + NetworkX
- FAISS in-memory
- PostgreSQL + Neo4j Community + Redis
- Docker Compose

### ADD (not in Prompt #2)
- `pikepdf` — to inject fake producer strings into demo PDFs
- `cryptography` (Ed25519 signing) — real digital signatures
- `weasyprint` or `reportlab` — PHANTOM Report PDF export
- `loguru` — structured logging
- `pytest` — smoke tests
- `react-dropzone` — explicitly in package.json
- A real frontend icon set: `lucide-react`

### DROP
- **Socket.io** (replaced by native WebSocket)
- **GraphSAGE / PyTorch Geometric** (untrainable on 40 nodes, install hell on Windows, no demo value)
- Any cloud LLM dependency in the demo path

### MAYBE (Phase 2 only, after MVP)
- **Gemini Flash** for narrative paragraph generation (progressive enhancement)
- **Render deploy** for remote-judge access

---

## 7. Architecture & data flow

### Folder structure (final)

```
phantom/
├── .env.example
├── .gitignore
├── README.md
├── docker-compose.yml
├── docker-compose.dev.yml          # infra-only stack for fast dev
├── PHANTOM_MASTER_PLAN.md          # this file
├── models/                          # gitignored, populated by download_models.py
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── download_models.py
│   ├── main.py
│   ├── config.py
│   ├── crypto/
│   │   └── signer.py                # Ed25519 signing
│   ├── database/
│   │   ├── postgres.py
│   │   └── neo4j_client.py
│   ├── schemas/
│   │   ├── application.py
│   │   ├── origin_certificate.py
│   │   └── phantom_report.py
│   ├── services/
│   │   ├── pdf_parser.py
│   │   ├── entropy_analyzer.py
│   │   ├── origin_engine.py
│   │   ├── graph_builder.py
│   │   ├── community_detection.py
│   │   ├── cross_signal_engine.py
│   │   ├── report_generator.py
│   │   ├── pdf_report_builder.py    # WeasyPrint export
│   │   └── narrative_writer.py      # f-string + optional Gemini
│   ├── ml/
│   │   ├── vit_inference.py
│   │   └── embedding_model.py
│   ├── api/
│   │   ├── deps.py
│   │   ├── ws_manager.py
│   │   └── routes/
│   │       ├── upload.py
│   │       ├── analyze.py
│   │       ├── results.py
│   │       ├── evidence.py          # signed bundle download
│   │       └── ws.py
│   ├── workers/
│   │   ├── celery_app.py
│   │   └── tasks.py
│   ├── seed/
│   │   └── init_demo_data.py
│   └── tests/
│       ├── test_origin_engine.py
│       └── test_cross_signal.py
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── theme/
│       │   ├── colors.js            # coldiq cream palette
│       │   └── typography.js
│       ├── pages/
│       │   ├── Landing.jsx
│       │   ├── Upload.jsx
│       │   └── Results.jsx
│       ├── components/
│       │   ├── Layout.jsx
│       │   ├── Hero.jsx
│       │   ├── DemoModeButton.jsx
│       │   ├── DropZone.jsx
│       │   ├── ApplicationCard.jsx
│       │   ├── FraudGraph.jsx       # D3 force-directed, cinematic
│       │   ├── OriginTree.jsx
│       │   ├── PhantomReport.jsx
│       │   ├── StatusToast.jsx
│       │   └── EvidenceHash.jsx
│       ├── hooks/
│       │   ├── useWebSocket.js
│       │   └── useAnalysis.js
│       ├── lib/
│       │   ├── api.js
│       │   └── formatters.js
│       └── data/
│           └── demo_dataset.js
│
└── demo_data/
    ├── generate_demo.py             # generates 40 PDFs with metadata injection
    ├── names_in.json                # pre-baked 40 Indian names
    └── pdfs/                        # output dir
```

### Data flow (end-to-end demo)

```
User clicks "Run Demo"
  │
  ▼
POST /analyze/demo
  │
  ▼
Backend ensures demo data seeded (idempotent)
  │
  ▼
Enqueues 40 Celery tasks: analyze_application(id)
  │       Each task:
  │         1. fetch PDF from PG
  │         2. pdf_parser → metadata + page image
  │         3. entropy_analyzer → 8-bucket profile
  │         4. vit_inference → 768-dim embedding (with 15s timeout)
  │         5. origin_engine → OriginCertificate (cbs_match_score, etc.)
  │         6. save certificate to PG
  │         7. broadcast WS: DOCUMENT_ANALYZED
  │
  ▼
After all 40 complete, enqueues analyze_batch(batch_id)
  │       Batch task:
  │         1. graph_builder → upsert Application nodes + edges into Neo4j
  │         2. community_detection → Louvain partitions
  │         3. cross_signal_engine → PHANTOM score per suspicious cluster
  │         4. report_generator → evidence bundle JSON
  │         5. crypto/signer → Ed25519 sign bundle
  │         6. pdf_report_builder → polished PDF
  │         7. narrative_writer → English summary (template, optional Gemini)
  │         8. broadcast WS: BATCH_COMPLETE with full graph + report
  │
  ▼
Frontend receives BATCH_COMPLETE
  │
  ▼
D3 graph: animate 11 ring nodes gray → red (800ms),
          glow edges, dim non-ring nodes
  │
  ▼
PHANTOM Report slides in from right
  │
  ▼
User clicks "Download Evidence Bundle"
  │
  ▼
GET /evidence/{ring_id}.pdf  →  signed PDF download
```

---

## 8. Design system — the "coldiq cream" theme

> **LOCKED on 2026-05-19.** User provided exact hex codes plus two reference screenshots from `coldiq.com` and `autoaudit.ai`. The palette is provisional — user may swap later — so all tokens live in `frontend/tailwind.config.js` + CSS vars, never as raw hex in components.

### Palette (locked)
| Token | Hex | Use |
|---|---|---|
| `cream-bg` | `#FAF5EA` | Page background |
| `cream-alt` | `#F4EDDD` | Alt section background |
| `border-light` | `#E8DFCB` | Subtle 1px borders |
| `border-strong` | `#D8CDB5` | Stronger borders |
| `ink` | `#1A1A1A` | Primary text + buttons (near-black) |
| `ink-muted` | `#6B655C` | Muted body text |
| `ink-placeholder` | `#9A938A` | Placeholders, captions |
| `accent` | `#4A8BC7` | Logo glyph only — do NOT over-use |
| `signal-red` | `#C8321F` | Fraud ring nodes / FREEZE_AND_ESCALATE |
| `signal-amber` | `#D4953A` | FLAG_FOR_REVIEW |
| `signal-green` | `#5C8A4A` | CLEAR / genuine documents |
| `dim-cream` | `#D4CFC2` | Non-ring nodes during reveal (interpolated) |

### Typography
- **Display / serif**: `"Instrument Serif"` or `"Cormorant Garamond"` (free via Google Fonts, italic-only for the mid-phrase in headlines)
- **Body sans**: `"Inter"` — UI text, labels, buttons, the bold parts of headlines
- **Mono**: `"JetBrains Mono"` — evidence hash, code, timestamps

### Signature headline pattern (from coldiq + autoaudit)
The hero headlines mix weights *within one line* — bold sans for the framing words and italic serif for the noun phrase. Examples:
- "Tomorrow's *GTM Systems* Built Today." (coldiq)
- "Tomorrow's *Compliance Engine* Built Today." (autoaudit)
- PHANTOM uses: **"Tomorrow's *Document Forensics* Built Today."** — or — **"Every PDF leaves a *fingerprint*. We find the *ring*."**

### Components — visual rules
- 1px solid borders (`border-light`), no drop shadows by default
- 12px corner radius on cards, fully rounded (`rounded-full`) for pills and CTA buttons
- Generous whitespace (multiples of 8px)
- Buttons: **solid black fill (`ink`) with white text** for primary CTAs; bordered/ghost for secondary. No coloured fills.
- A "pill badge" sits above the hero headline (`FOR [audience] [scale qualifier] →`) with a tiny black circle + arrow on the right edge — directly copy this element.
- The fraud graph background is **cream**, not dark — makes the red ring nodes pop dramatically
- The PHANTOM Report panel is a slide-in **white-paper card** with serif header — looks like a real document, not a dashboard

### The cinematic reveal moment
1. Graph renders, all 40 nodes in soft gray (`#8A8478`)
2. WebSocket BATCH_COMPLETE arrives
3. Non-ring 29 nodes fade to `#D4CFC2` (dimmer cream) over 600ms
4. Ring 11 nodes scale up to 1.4x with stagger (50ms each) and transition fill to `signal-red`
5. Ring edges fade in with red stroke + glow filter
6. PHANTOM Report panel slides in from right with subtle shadow
7. Audio cue (optional): single soft "ping" tone — judges remember sound

---

## 9. Phased build plan

### Phase 1 — MVP (Days 1–7)

**Day 1: Foundation**
- `git init`, push to GitHub
- Folder scaffolding per Section 7
- `download_models.py`, run it, confirm `./models/` populated
- `docker-compose.yml` for infra only (Postgres, Neo4j, Redis) + healthchecks
- `.env.example` with all keys
- `requirements.txt`, `package.json`

**Day 2: Backend core**
- `database/postgres.py`, `database/neo4j_client.py` connection clients
- `schemas/` Pydantic models
- `services/pdf_parser.py` with PyMuPDF
- `services/entropy_analyzer.py` with scipy
- `ml/vit_inference.py` with 15s timeout + graceful fallback
- `services/origin_engine.py` combining signals into OriginCertificate

**Day 3: Demo data generator**
- `demo_data/generate_demo.py`
- ReportLab to generate 40 salary slips
- **pikepdf post-processing to inject `Canva 2.0` producer for the 11 fraud docs and `CBS-Finacle-7.3` etc for clean ones**
- 11 fraud docs: same `font_subset_hash`, timestamps in 16-min window
- Pre-baked Indian names in `names_in.json`
- Run it, manually verify metadata via `pikepdf` REPL

**Day 4: Graph + scoring**
- `services/graph_builder.py` builds Neo4j graph
- `services/community_detection.py` runs Louvain
- `services/cross_signal_engine.py` with **exact formulas from Prompt #2 Section "CROSS-SIGNAL SCORING — PRECISE DEFINITION"**
- `crypto/signer.py` for Ed25519
- `services/report_generator.py` builds evidence bundle + signs

**Day 5: API + Celery + WebSocket**
- `workers/celery_app.py`, `workers/tasks.py`
- `api/routes/upload.py`, `analyze.py`, `results.py`, `evidence.py`, `ws.py`
- `api/ws_manager.py` connection manager
- `main.py` with lifespan that creates tables/constraints + seeds if empty
- `seed/init_demo_data.py`
- Test end-to-end with `curl` + `wscat`

**Day 6: Frontend skeleton**
- Vite + Tailwind + Framer Motion + D3 + lucide-react setup
- `theme/colors.js` + `theme/typography.js` (the cream palette)
- `pages/Landing.jsx`, `pages/Upload.jsx`, `pages/Results.jsx`
- `hooks/useWebSocket.js` (native WebSocket, auto-reconnect)
- `components/DropZone.jsx`, `ApplicationCard.jsx`, `DemoModeButton.jsx`
- Wire up real-time progress

**Day 7: The money moment**
- `components/FraudGraph.jsx` — D3 force-directed
- Implement the cinematic reveal with `d3.transition()` + Framer Motion overlay
- `components/PhantomReport.jsx` — slide-in panel
- `components/OriginTree.jsx` — per-document forensic detail
- `components/EvidenceHash.jsx` — monospace hash display with copy
- Full demo rehearsal end-to-end
- Smoke tests in `backend/tests/`

### Phase 2 — Polish (Days 8–9)

**Day 8: Document polish**
- `services/pdf_report_builder.py` — WeasyPrint PHANTOM Report PDF
- `services/narrative_writer.py` — f-string template + optional Gemini Flash
- Add Gemini API key handling (`.env` toggle, never required)
- Loguru structured logging
- `/health` endpoint with DB pings

**Day 9: Visual polish**
- Refine theme to match exact "coldiq cream" reference (user to provide)
- Microinteractions: hover states, focus rings, loading skeletons
- Empty states, error states, network-failure toast
- Keyboard shortcuts (`D` for demo mode, `Esc` to close report)
- Audio cue on reveal (optional, off by default)
- Mobile-responsive (judges may demo on tablet)

### Phase 3 — Startup-pitch (Days 10+)

**Day 10: Documentation + pitch**
- `README.md` with hero pitch, screenshots, install instructions
- Architecture diagram (mermaid in README, plus a separate PNG)
- Demo GIF (record with OBS, trim to 15s)
- 60-second pitch script
- Deploy backend to Render (optional, for remote judge link)
- Deploy frontend to Vercel (optional)

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ViT inference too slow on user's CPU | Medium | High | 15s timeout + graceful fallback; redistribute weight to other signals |
| Docker eats too much RAM on Windows | Medium | High | Dev mode runs FastAPI/Celery natively; only infra in Docker |
| ReportLab won't fake producer string | Was certain — **fixed via pikepdf** | High | Post-process every PDF with pikepdf |
| Hackathon WiFi dies on stage | High | High | Demo Mode button + all models offline + signed local artifacts |
| Judge questions "what's your training data?" | High | Medium | Honest answer: rule-based forensics, not ML classification. Pivot to "we don't need training data — physics of file formats is deterministic" |
| Judge questions "is SHA-256 a signature?" | Medium | Medium | **Pre-empted by switching to Ed25519** |
| D3 animation glitches | Medium | High | Build + record GIF as fallback; PowerPoint backup with the screenshots |
| Celery worker doesn't start | Low | High | Healthcheck + retry; or run in `--threads` mode in FastAPI for hackathon if Celery flakes |
| Demo data seed fails silently | Low | Critical | Loud error + halt on seed failure; `/health` endpoint checks seed status |
| Neo4j memory limits | Low | Medium | Set `NEO4J_dbms_memory_heap_max__size=512M` in compose |

---

## 11. Accounts & one-time setup checklist

### Must-have (do these first)
- [ ] GitHub account + repo `phantom-fraud` created
- [ ] Docker Desktop installed on Windows with WSL2 enabled
- [ ] Python 3.11 installed (matches Docker image)
- [ ] Node 20+ installed
- [ ] `pip install -r backend/requirements.txt` succeeds locally (verify before Docker)
- [ ] `npm install` in `frontend/` succeeds
- [ ] `python backend/download_models.py` run once; `models/` populated

### Nice-to-have (Phase 2/3)
- [ ] Google AI Studio key for Gemini (free, no card)
- [ ] Render account + GitHub link for hosted backend
- [ ] Vercel account for hosted frontend
- [ ] ngrok account + auth token saved (offline backup)
- [ ] OBS Studio installed (for demo recording)

### Skip
- [ ] ~~OpenAI / Anthropic API~~ (paid)
- [ ] ~~Pinecone~~ (use FAISS)
- [ ] ~~AWS/GCP/Azure~~ (free tier overkill for hackathon)
- [ ] ~~Neo4j AuraDB~~ (Community in Docker)

---

## 12. What this project WILL be — in simple English

When this project is built and demo-ready, here is what you can honestly say it does:

1. **It takes 40 loan application PDFs and figures out which ones were created by fraudsters working together.** Not by guessing — by reading the hidden fingerprints inside each PDF file (what software made it, when it was made, what fonts it uses, how the file is compressed).

2. **It looks at each document on its own first.** For every PDF, it produces an "Origin Certificate" that says: "This document was made by [Canva / Microsoft Word / a real Core Banking System]. Confidence: [X%]." This is the document forensics layer.

3. **Then it looks at all documents together as a network.** It builds a graph where each loan applicant is a dot, and lines connect applicants who share suspicious patterns — same timing, same document template, same guarantor. A community-detection algorithm finds clusters that should not exist.

4. **It combines both views into one number.** A "PHANTOM Confidence Score" from 0 to 100% says "yes, this is a fraud ring" or "no, looks fine." The formula is precise and reproducible.

5. **It produces a court-ready evidence bundle.** A signed PDF with the Ed25519 signature, the evidence hash, the list of ring members, the timeline, and a plain-English summary paragraph. This is the deliverable for a fraud officer.

6. **It runs entirely on the laptop.** One command (`docker-compose up`) starts everything. No internet needed during the demo. If the venue WiFi dies, the demo still works.

7. **It has a "Demo Mode" button.** One click and the whole 40-application analysis runs against pre-seeded data. No file uploads needed. This is the safety net for the live presentation.

8. **The visual reveal is the wow moment.** Forty gray dots on a cream canvas. You click Demo. Eleven of them slowly turn red and connect with glowing lines while the others fade. A slide-in report says "Fraud ring confirmed. 11 entities. ₹6.2 crore at risk. Confidence 97%. FREEZE AND ESCALATE."

9. **It looks like a real product.** Coldiq-cream theme, serif headlines, editorial typography, premium spacing. Not a hackathon dashboard — a fintech product. Judges and investors will register this in the first 3 seconds.

10. **It is unique because of its angle.** Every other fraud detection demo asks "is this document fake?" PHANTOM asks "where was this document born?" That reframing is the moat. It's a question that gets sharper as deepfakes get better — fakes can match visual content, but they can't easily fake the entire file-format provenance chain.

---

## 13. What this project will NOT be

Being honest so we don't oversell:

1. **It is NOT a trained machine learning model that learned to spot fraud.** Most of the detection power comes from rule-based forensics on file metadata and a community-detection algorithm. The ML pieces (ViT, sentence-transformers) are supporting features, not the brain. We can still pitch the ML angle, but a sharp judge who asks "what's your F1 score on a held-out set?" will get an honest answer: "we don't have a labeled dataset; we have a deterministic forensics pipeline that works without one."

2. **It does NOT detect fraud rings that don't share document signals.** If 11 fraudsters used 11 different tools and submitted at random times, PHANTOM finds nothing unusual. The detection is conditional on the ring being lazy (which most real rings are — they reuse templates because making 11 unique fake salary slips is tedious).

3. **It does NOT generalize beyond loan applications without re-tuning.** The signal weights are calibrated to the demo. A real deployment would need re-calibration against the bank's actual document corpus.

4. **It is NOT a replacement for a fraud officer.** It produces evidence; humans decide. The "FREEZE AND ESCALATE" recommendation is a recommendation, not an action.

5. **It does NOT use a real Core Banking System fingerprint corpus.** The "CBS centroid" comparison is partly theatrical — there's no real CBS document corpus to compare against. We use heuristic rules (producer string matching) as the main signal. In production, the bank would feed us a corpus of their genuine documents to build a real centroid.

6. **GraphSAGE is NOT in the final build.** It's been dropped. Louvain + the rule-based score is enough for the demo and avoids 1 GB of install pain for zero added accuracy on 40 nodes.

7. **The LLM is NOT a load-bearing component.** The narrative paragraph uses a template by default. If a Gemini API key is configured, it gets used as an enhancement. The demo cannot fail because of an LLM API outage.

8. **It is NOT deployed-to-cloud by default.** It runs on the laptop. Render / Vercel deploys are Phase 3 niceties for remote judge access, not the primary delivery vehicle.

9. **It does NOT handle 10,000 documents.** Calibrated for 40. The architecture would scale (Celery scales horizontally, Neo4j scales, FAISS scales to millions) but we haven't load-tested.

10. **It does NOT include user authentication, multi-tenant isolation, audit logs, or any of the production-readiness work a real bank would require.** Those are Phase 4+ if this becomes a startup.

---

## 14. Locked-in upgrades — Points 2 & 5 are IN SCOPE

These were originally in the "will not be" list. As of this revision, they are committed scope. Points 1, 3, 8, 10 remain deferred — to be reconsidered after MVP ships.

### Upgrade A — Multi-signal detection (Point 2)

**What changes:** PHANTOM stops being purely a document-forensics tool. It also looks at PII overlap and free-text similarity. A fraud ring that uses different document templates but shares phone prefixes — or writes their "purpose of loan" field in suspiciously similar language — now gets caught.

**Three signals to add:**

1. **PII overlap graph** — for every pair of applications, compute:
   - First 6 digits of bank account match → edge weight +0.3
   - Same IFSC branch → +0.2
   - Same phone prefix (first 6 digits) → +0.3
   - Same email domain (excluding gmail/yahoo/outlook) → +0.4
   - PAN first 4 chars match → +0.2
   Threshold > 0.5 → add `SHARED_PII` edge in Neo4j

2. **Form-text similarity** — extract free-text fields (`purpose_of_loan`, `employer_description`, `address_line_2`), embed with `sentence-transformers/all-MiniLM-L6-v2`, cosine similarity > 0.85 → add `TEXT_MATCH` edge. This is what finally makes sentence-transformers earn its keep.

3. **Name fuzzy match** — Levenshtein distance < 3 OR Soundex match between applicant names → add `NAME_SIMILARITY` edge (catches `Rahul Sharma` / `Rahul Sharrma` / `R Sharma`).

**Where it plugs in:**
- New file: `backend/services/pii_signals.py`
- New file: `backend/services/text_similarity.py`
- New file: `backend/services/name_match.py`
- `graph_builder.py` adds the new edge types
- `cross_signal_engine.py` updated formula:

```
behavioral_score now includes:
  + pii_overlap_fraction × 0.15
  + text_similarity_fraction × 0.15
  + name_similarity_fraction × 0.10
(reweight existing components down proportionally)
```

**Demo impact:** in the 40-app dataset, the 11 fraud ring members also share:
- 3 sub-groups using same phone prefix `+91 98765`
- All 11 list "small business expansion" verbatim in `purpose_of_loan`
- Two pairs are near-duplicate names

When PHANTOM runs, the graph now shows multiple edge colors (template-match red, PII orange, text-match purple) — visually richer reveal.

**Cost: 1.5–2 days, ₹0.**

### Upgrade B — Synthetic CBS reference corpus (Point 5)

**What changes:** the "CBS centroid" stops being theatrical. We build it.

**Build steps:**

1. New script: `backend/seed/build_cbs_corpus.py` — generates 100 synthetic "genuine bank" PDFs at first startup. Mix:
   - 40 with producer `Finacle 7.3` / creator `Finacle Report Engine`
   - 30 with producer `TCS BaNCS 9.1`
   - 20 with producer `Oracle FLEXCUBE 12.4`
   - 10 with producer `Temenos T24`
   Each gets realistic Indian-bank styling (header logo placeholder, columnar layout, fixed-width fonts, branch/IFSC footer). pikepdf injects metadata after ReportLab generation.

2. For each of the 100, compute and save:
   - 8-bucket entropy profile
   - 768-dim ViT CLS embedding
   - Font subset hash
   - Tool category

3. Aggregate into a reference object:
   - `mean_entropy_profile`: element-wise mean of 100 profiles (8 floats)
   - `entropy_covariance`: per-bucket variance (for Mahalanobis distance later)
   - `mean_vit_embedding`: 768-dim L2-normalized mean
   - `vit_embedding_std`: per-dim standard deviation
   - `expected_font_subset_hashes`: set of all hashes seen across 100 docs
   - `producer_whitelist`: set of producer strings

4. Save to `models/cbs_reference.pkl` — loaded once into memory at FastAPI startup.

5. `origin_engine.py` distance computations:
   - `entropy_distance = cosine_distance(doc_entropy_profile, mean_entropy_profile)`
   - `vit_distance = 1 - cosine_similarity(doc_vit_embedding, mean_vit_embedding)`
   - `producer_match = 1.0 if doc_producer in producer_whitelist else 0.0`
   - `cbs_match_score` is now a proper weighted distance, not a heuristic

**Honesty disclosure for the pitch:** "Our reference corpus is currently 100 synthetic CBS-style documents we generated ourselves. In production deployment, this would be rebuilt from a sample of the bank's actual genuine documents — typically 500–1000 PDFs — in under an hour." This is a *strength* in the pitch: shows the system is bank-tunable, not pre-baked.

**Cost: 1 day, ₹0.**

### Updated time budget

| Phase | Days |
|---|---|
| Phase 1 MVP (original) | 7 |
| Upgrade A (multi-signal) | 1.5–2 |
| Upgrade B (CBS corpus) | 1 |
| **New MVP+ total** | **9.5–10** |
| Phase 2 polish | 2 |
| Phase 3 pitch | 1 |
| **All-in total** | **12.5–13 days, ₹0** |

### Updated folder additions

```
backend/
├── services/
│   ├── pii_signals.py        # NEW — Upgrade A
│   ├── text_similarity.py    # NEW — Upgrade A
│   └── name_match.py         # NEW — Upgrade A
├── seed/
│   └── build_cbs_corpus.py   # NEW — Upgrade B
models/
└── cbs_reference.pkl         # NEW — Upgrade B, gitignored
```

### Section 13 corrections

Items 2 and 5 in the "WILL NOT be" list are no longer accurate after these upgrades:

- **Item 2 (rings without shared doc signals)** → now reads: PHANTOM detects rings that share **documents OR PII OR free-text patterns OR similar names**. It still won't catch rings that share *none* of these — but such rings would look invisible to any system.
- **Item 5 (no real CBS corpus)** → fully resolved. We now build a synthetic-but-real-computed CBS reference corpus and measure actual distances against it.

The other 8 "WILL NOT" items still stand until/unless they're moved into scope.

---

## Final note

Read this document end-to-end before writing the first line of code. Every decision in it has a reason. When in doubt, prefer the choice that makes the **demo bulletproof** over the choice that makes the **architecture impressive**. A judge sees 30 seconds of demo and 90 seconds of pitch. The code never gets read. Build for those 2 minutes.

The build is approximately 7 days for MVP, +2 days for polish, +1 day for pitch. If time is tighter, Phase 2 and Phase 3 are sacrificeable. Phase 1 is not.

**Next step**: confirm this plan, share the coldiq cream theme reference (Figma file, screenshots, or hex codes), and I'll start with Day 1 — folder scaffolding + Docker infra + `download_models.py`.
