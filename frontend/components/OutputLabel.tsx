import type { OutputLabel as Label } from "@/lib/api";

// Hard rule 4: every output says whether it is a document fact, a company claim,
// a Python calculation or an AI interpretation.
const STYLES: Record<Label, string> = {
  "verified fact (from the document)":
    "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:ring-emerald-800",
  "company claim (disclosed risk factor)":
    "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-800",
  "calculated metric":
    "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-950 dark:text-sky-200 dark:ring-sky-800",
  "AI interpretation":
    "bg-violet-50 text-violet-800 ring-violet-200 dark:bg-violet-950 dark:text-violet-200 dark:ring-violet-800",
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
    <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
      <span>Labels:</span>
      {(Object.keys(STYLES) as Label[]).map((label) => (
        <OutputLabel key={label} label={label} />
      ))}
    </div>
  );
}
