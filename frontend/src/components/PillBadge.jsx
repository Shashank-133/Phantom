import { ArrowUpRight } from "lucide-react";

// The signature "FOR [audience]" pill above every hero — mirrors the exact
// visual treatment from coldiq.com and autoaudit.ai. Optional onClick lets
// it act as a CTA to anchor sections / scroll-to / external link.
export default function PillBadge({ children, onClick, as = "div" }) {
  const Tag = as;
  return (
    <Tag
      onClick={onClick}
      className={`pill-badge ${onClick ? "cursor-pointer transition-colors hover:bg-cream-alt" : ""}`}
    >
      <span>{children}</span>
      <span className="pill-badge-arrow" aria-hidden>
        <ArrowUpRight size={14} strokeWidth={2.25} />
      </span>
    </Tag>
  );
}
