import type { OutputLabel as Label } from "@/lib/api";

// Hard rule 4: every output says whether it is a document fact, a company claim,
// a Python calculation or an AI interpretation.
const STYLES: Record<Label, string> = {
  "verified fact (from the document)": "text-accent ring-accent/25 bg-accent-soft",
  "company claim (disclosed risk factor)": "text-[#8a5a12] ring-[#8a5a12]/25 bg-[#f7efe1]",
  "calculated metric": "text-[#2f4a7a] ring-[#2f4a7a]/25 bg-[#eaf0f8]",
  "AI interpretation": "text-[#6a3f86] ring-[#6a3f86]/25 bg-[#f2ebf7]",
};

const SHORT: Record<Label, string> = {
  "verified fact (from the document)": "Verified fact",
  "company claim (disclosed risk factor)": "Company claim",
  "calculated metric": "Calculated metric",
  "AI interpretation": "AI interpretation",
};

export function OutputLabel({ label }: { label: Label }) {
  return (
    <span
      title={label}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${STYLES[label]}`}
    >
      {SHORT[label]}
    </span>
  );
}

export function LabelLegend() {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
      {(Object.keys(STYLES) as Label[]).map((label) => (
        <OutputLabel key={label} label={label} />
      ))}
    </div>
  );
}
