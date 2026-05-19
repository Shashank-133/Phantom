// Loading skeleton matching ApplicationCard's height. Renders a soft pulse so
// the live-feed panel never looks empty during the first second of analysis,
// when the WebSocket is connected but no DOCUMENT_ANALYZED events have
// landed yet.
export default function SkeletonCard() {
  return (
    <div
      className="card flex animate-pulse items-center gap-4 px-5 py-3"
      aria-hidden
    >
      <div className="h-10 w-10 rounded-lg bg-cream-alt" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-2/3 rounded bg-cream-alt" />
        <div className="h-2.5 w-1/3 rounded bg-cream-alt/70" />
      </div>
      <div className="space-y-1.5 text-right">
        <div className="ml-auto h-3 w-12 rounded bg-cream-alt" />
        <div className="ml-auto h-2 w-8 rounded bg-cream-alt/70" />
      </div>
    </div>
  );
}
