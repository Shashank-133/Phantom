import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Fingerprint,
  Network,
  ShieldCheck,
  FileSignature,
  ArrowRight,
} from "lucide-react";
import PillBadge from "../components/PillBadge";

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};
const fade = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] } },
};

function Pillar({ icon: Icon, kicker, title, body }) {
  return (
    <motion.div variants={fade} className="card p-6">
      <div className="mb-4 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-cream-alt text-ink">
        <Icon size={18} />
      </div>
      <p className="mb-1 text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
        {kicker}
      </p>
      <h3 className="mb-2 text-lg font-semibold text-ink">{title}</h3>
      <p className="text-sm leading-relaxed text-ink-muted">{body}</p>
    </motion.div>
  );
}

export default function Landing() {
  return (
    <>
      {/* Hero — copies coldiq/autoaudit composition exactly: centred pill,
          mixed-weight headline, muted subtitle, two CTAs. */}
      <section className="mx-auto flex max-w-6xl flex-col items-center px-6 pt-16 pb-24 text-center md:pt-24 md:pb-32">
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <PillBadge>
            For Indian banks reviewing &gt; 100 loan applications / month
          </PillBadge>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="mt-8 max-w-5xl text-display-xl font-bold text-ink"
        >
          Every PDF leaves a{" "}
          <span className="font-serif font-normal italic text-ink">fingerprint</span>.
          <br />
          We find the{" "}
          <span className="font-serif font-normal italic text-ink">ring</span>.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.25 }}
          className="mt-7 max-w-2xl text-base leading-relaxed text-ink-muted md:text-lg"
        >
          PHANTOM reads the hidden metadata, fonts, and compression signatures
          inside every loan document — then maps the cross-applicant graph to
          surface fraud rings before a single rupee is disbursed.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="mt-10 flex flex-col items-center gap-3 sm:flex-row"
        >
          <Link to="/upload" className="btn-primary">
            Run a live demo
            <ArrowRight size={16} />
          </Link>
          <a
            href="#how-it-works"
            className="btn-secondary"
            onClick={(e) => {
              e.preventDefault();
              document
                .getElementById("how-it-works")
                ?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            How it works
          </a>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-ink-muted"
        >
          <span>40 applications · 2.3 seconds</span>
          <span aria-hidden>·</span>
          <span>Ed25519 signed evidence</span>
          <span aria-hidden>·</span>
          <span>Runs fully offline</span>
        </motion.div>
      </section>

      {/* Capability pillars — four-up grid. Editorial, no shadows. */}
      <section
        id="how-it-works"
        className="border-y border-border-light bg-cream-alt/40"
      >
        <div className="mx-auto max-w-7xl px-6 py-20 md:py-28">
          <div className="mb-14 max-w-2xl">
            <p className="mb-3 text-[0.65rem] font-medium uppercase tracking-[0.18em] text-ink-muted">
              How it works
            </p>
            <h2 className="text-display-md font-bold text-ink">
              Two engines.{" "}
              <span className="font-serif font-normal italic">One verdict.</span>
            </h2>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-ink-muted">
              PHANTOM splits document forensics from network forensics — then
              cross-references both. A document that looks fine alone can still
              betray itself in the graph.
            </p>
          </div>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-100px" }}
            className="grid gap-4 md:grid-cols-2 lg:grid-cols-4"
          >
            <Pillar
              icon={Fingerprint}
              kicker="Engine 1"
              title="Document origin"
              body="ViT embeddings, entropy profile, font-subset hash and producer metadata are scored against a reference corpus of genuine bank documents."
            />
            <Pillar
              icon={Network}
              kicker="Engine 2"
              title="Network forensics"
              body="Pairwise PII, text-similarity, timing, valuer and guarantor edges feed a Louvain community search to surface anomalous clusters."
            />
            <Pillar
              icon={ShieldCheck}
              kicker="Scoring"
              title="PHANTOM Score"
              body="Behavioural and origin signals merge into one [0, 100%] verdict — Clear, Flag for Review, or Freeze & Escalate — with explicit weights."
            />
            <Pillar
              icon={FileSignature}
              kicker="Evidence"
              title="Court-ready bundle"
              body="Every ring exports a canonical JSON evidence bundle signed with an Ed25519 keypair held on the bank's side. Public key fetchable on demand."
            />
          </motion.div>
        </div>
      </section>

      {/* The closer — direct CTA with the same hero treatment, scaled down. */}
      <section className="mx-auto max-w-5xl px-6 py-24 text-center md:py-32">
        <PillBadge>Ready when you are</PillBadge>
        <h2 className="mt-8 text-display-lg font-bold text-ink">
          See the ring{" "}
          <span className="font-serif font-normal italic">reveal itself</span>.
        </h2>
        <p className="mx-auto mt-6 max-w-xl text-base text-ink-muted md:text-lg">
          Forty seeded applications. Eleven of them belong to the same
          fraud ring. Watch PHANTOM find them in under three seconds.
        </p>
        <div className="mt-10">
          <Link to="/upload" className="btn-primary">
            Start the demo
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </>
  );
}
