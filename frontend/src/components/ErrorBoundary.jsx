import { Component } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

// Last-line-of-defence for runtime React errors. Without this a single throw
// in a deep component (D3 ref glitch, async state-after-unmount, etc.) would
// blank the entire page — which on stage looks worse than any caught bug.
//
// In dev we still surface the stack so you can find the cause; in prod the
// user sees a calm "Something went sideways" card with a reload button.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("PHANTOM UI crashed:", error, info.componentStack);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    const isDev = typeof import.meta !== "undefined" && import.meta.env?.DEV;
    return (
      <section className="mx-auto max-w-2xl px-6 py-24 text-center">
        <div className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-signal-red/10 text-signal-red">
          <AlertTriangle size={22} />
        </div>
        <h1 className="mt-6 text-display-md font-bold text-ink">
          Something went{" "}
          <span className="font-serif font-normal italic">sideways</span>.
        </h1>
        <p className="mt-4 text-ink-muted">
          The interface tripped on an error. Your data is safe — reloading will
          recover the view.
        </p>
        {isDev && this.state.error && (
          <pre className="mt-6 overflow-auto rounded-card border border-border-light bg-cream-alt p-4 text-left font-mono text-xs text-ink-muted">
            {String(this.state.error?.message || this.state.error)}
          </pre>
        )}
        <div className="mt-8 flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="btn-primary"
          >
            <RotateCcw size={15} /> Reload PHANTOM
          </button>
          <button type="button" onClick={this.reset} className="btn-secondary">
            Try to recover
          </button>
        </div>
      </section>
    );
  }
}
