import { NavLink, Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Keyboard, Menu, X } from "lucide-react";
import { api } from "../lib/api";
import { useWebSocket } from "../hooks/useWebSocket";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import NetworkBanner from "./NetworkBanner";
import ShortcutHelp from "./ShortcutHelp";

// Cream page chrome. Header copies coldiq/autoaudit: small mark on the left,
// centred nav, single dark CTA on the right. The "live" dot pings /health
// every 15s so judges can see the backend is reachable.
function StatusDot() {
  const [healthy, setHealthy] = useState(null);
  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      try {
        await api.health();
        if (mounted) setHealthy(true);
      } catch {
        if (mounted) setHealthy(false);
      }
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);
  const color =
    healthy === null
      ? "bg-ink-placeholder"
      : healthy
      ? "bg-signal-green"
      : "bg-signal-red";
  const label =
    healthy === null ? "Checking…" : healthy ? "System live" : "Backend offline";
  return (
    <div className="flex items-center gap-2 text-xs text-ink-muted">
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`}>
        {healthy && (
          <span className="absolute inset-0 animate-ping rounded-full bg-signal-green opacity-50" />
        )}
      </span>
      <span>{label}</span>
    </div>
  );
}

function Brand() {
  return (
    <Link
      to="/"
      className="group inline-flex items-center gap-2.5 text-ink"
      aria-label="PHANTOM home"
    >
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-ink">
        <span className="block h-2 w-2 rounded-full bg-accent" />
      </span>
      <span className="text-[0.95rem] font-semibold tracking-[0.18em] uppercase">
        Phantom
      </span>
    </Link>
  );
}

function NavLinkItem({ to, children, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        `text-sm transition-colors duration-200 ${
          isActive ? "text-ink" : "text-ink-muted hover:text-ink"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function Layout({ children }) {
  const [helpOpen, setHelpOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  // We watch WS status here so the banner shows up no matter which page is
  // active. It's cheap — a single dedicated connection at the shell.
  const { status: wsStatus } = useWebSocket("/ws");

  // Global shortcuts that should work on every page.
  useKeyboardShortcuts({
    "?": () => setHelpOpen((v) => !v),
    "/": () => setHelpOpen((v) => !v),
    Escape: () => {
      setHelpOpen(false);
      setMobileNavOpen(false);
    },
  });

  return (
    <div className="min-h-screen cream-grain">
      <NetworkBanner wsStatus={wsStatus} />

      <header className="sticky top-0 z-30 border-b border-border-light bg-cream-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Brand />

          {/* Desktop nav */}
          <nav className="hidden items-center gap-8 md:flex" aria-label="Main">
            <NavLinkItem to="/">Overview</NavLinkItem>
            <NavLinkItem to="/upload">Analyse</NavLinkItem>
            <NavLinkItem to="/results">Results</NavLinkItem>
          </nav>

          <div className="flex items-center gap-2 sm:gap-4">
            <div className="hidden md:block">
              <StatusDot />
            </div>
            <button
              type="button"
              onClick={() => setHelpOpen(true)}
              className="hidden h-9 w-9 items-center justify-center rounded-full border border-border-light text-ink-muted transition-colors hover:bg-cream-alt focus:outline-none focus-visible:ring-2 focus-visible:ring-ink sm:inline-flex"
              aria-label="Keyboard shortcuts"
              title="Keyboard shortcuts (press ?)"
            >
              <Keyboard size={14} />
            </button>
            <Link to="/upload" className="btn-primary py-2.5 px-5 text-xs sm:py-3.5 sm:px-7 sm:text-sm">
              Run Demo
            </Link>
            <button
              type="button"
              onClick={() => setMobileNavOpen((v) => !v)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border-light text-ink-muted transition-colors hover:bg-cream-alt md:hidden"
              aria-label="Toggle menu"
              aria-expanded={mobileNavOpen}
            >
              {mobileNavOpen ? <X size={15} /> : <Menu size={15} />}
            </button>
          </div>
        </div>

        {/* Mobile nav drawer */}
        {mobileNavOpen && (
          <nav
            className="border-t border-border-light bg-cream-bg px-6 py-4 md:hidden"
            aria-label="Mobile"
          >
            <ul className="flex flex-col gap-3">
              <li>
                <NavLinkItem to="/" onClick={() => setMobileNavOpen(false)}>
                  Overview
                </NavLinkItem>
              </li>
              <li>
                <NavLinkItem to="/upload" onClick={() => setMobileNavOpen(false)}>
                  Analyse
                </NavLinkItem>
              </li>
              <li>
                <NavLinkItem to="/results" onClick={() => setMobileNavOpen(false)}>
                  Results
                </NavLinkItem>
              </li>
            </ul>
            <div className="mt-4 border-t border-border-light pt-4">
              <StatusDot />
            </div>
          </nav>
        )}
      </header>

      <main>{children}</main>

      <footer className="border-t border-border-light bg-cream-alt/40">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-4 px-6 py-8 text-xs text-ink-muted md:flex-row md:items-center">
          <div className="flex items-center gap-2">
            <span>PHANTOM</span>
            <span aria-hidden>·</span>
            <span>Document Origin Intelligence</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
            <span>SuRaksha Cyber Hackathon 2.0</span>
            <span aria-hidden>·</span>
            <span className="font-mono">Ed25519 signed evidence</span>
            <span aria-hidden>·</span>
            <button
              type="button"
              onClick={() => setHelpOpen(true)}
              className="font-mono underline-offset-2 hover:underline"
            >
              ? shortcuts
            </button>
          </div>
        </div>
      </footer>

      <ShortcutHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
