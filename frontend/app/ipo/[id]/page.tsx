import Link from "next/link";
import { notFound } from "next/navigation";

import { AskBox } from "@/components/AskBox";
import { Citation, Citations } from "@/components/Citation";
import { Disclaimer } from "@/components/Disclaimer";
import { type ChartPoint, FinancialsChart } from "@/components/FinancialsChart";
import { HeadlineFigures, StatusPill, bidWindow, priceBandText } from "@/components/Ipo";
import { LabelLegend, OutputLabel } from "@/components/OutputLabel";
import { api, type Figure, type IssueFact, type Metric, type Risk } from "@/lib/api";
import {
  CATEGORY_NAMES,
  FIELD_NAMES,
  formatDate,
  formatNumber,
  metricName,
  periodName,
  sortPeriods,
  unitCaption,
} from "@/lib/format";

export const dynamic = "force-dynamic";

const FLOW_METRICS = [
  "revenue_from_operations",
  "other_income",
  "total_income",
  "finance_costs",
  "depreciation_amortisation",
  "profit_before_tax",
  "total_tax_expense",
  "profit_after_tax",
  "eps_basic",
  "eps_diluted",
  "net_cash_from_operating_activities",
];
const BALANCE_METRICS = [
  "total_assets",
  "equity_share_capital",
  "other_equity",
  "non_controlling_interest",
  "total_equity",
  "borrowings_non_current",
  "borrowings_current",
  "deferred_payment_liabilities_non_current",
  "deferred_payment_liabilities_current",
  "cash_and_cash_equivalents",
];
const KEY_FACTS = [
  "fresh_issue_amount",
  "fresh_issue_shares",
  "offer_for_sale_amount",
  "total_issue_amount",
  "face_value",
  "price_band",
  "anchor_bid_date",
  "bid_open_date",
  "bid_close_date",
];

export default async function IpoPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id)) notFound();
  let document;
  try {
    document = await api.document(id);
  } catch {
    notFound();
  }
  const [financials, issue, risks, ipos] = await Promise.all([
    api.financials(id),
    api.issue(id),
    api.risks(id),
    api.ipos(),
  ]);
  const basis = financials.figures[0]?.basis;
  const ipo = ipos.find((i) => i.documents.some((d) => d.id === id));
  const window = ipo ? bidWindow(ipo) : null;
  const others = ipo?.documents.filter((d) => d.id !== id) ?? [];

  return (
    <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-14">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← All IPOs
      </Link>
      <header className="mt-6 border-b border-hairline pb-10">
        <div className="flex flex-wrap items-center gap-3">
          {ipo && <StatusPill status={ipo.status} />}
          <span className="text-sm text-muted">
            {document.doc_type}
            {document.filing_date ? `, dated ${formatDate(document.filing_date)}` : ""} ·{" "}
            {document.page_count} pages
            {basis ? ` · ${basisName(basis)} financials` : ""}
          </span>
        </div>
        <h1 className="mt-3 text-4xl text-ink sm:text-5xl">{document.company}</h1>

        {ipo && (
          <dl className="mt-6 grid grid-cols-1 gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs uppercase tracking-wider text-muted">Bidding</dt>
              <dd className="mt-1 text-base text-ink">
                {window ?? "Dates not printed"}
                {ipo.bid_open && (
                  <Citation documentId={ipo.bid_open.document_id} page={ipo.bid_open.page_no} />
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wider text-muted">Price band</dt>
              <dd className="mt-1 text-base text-ink">
                {priceBandText(ipo.price_band, ipo.status)}
                {ipo.price_band && (
                  <Citation documentId={ipo.price_band.document_id} page={ipo.price_band.page_no} />
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wider text-muted">Also filed</dt>
              <dd className="mt-1 text-base text-ink">
                {others.length === 0
                  ? "—"
                  : others.map((d) => (
                      <span key={d.id} className="mr-2 capitalize">
                        {d.doc_type}
                        {d.filing_date ? ` (${formatDate(d.filing_date)})` : ""}
                      </span>
                    ))}
              </dd>
            </div>
          </dl>
        )}

        {ipo && (
          <div className="mt-10 rounded-2xl border border-hairline bg-card p-6 sm:p-8">
            <HeadlineFigures ipo={ipo} />
          </div>
        )}

        <div className="mt-6 flex flex-col gap-3">
          <Disclaimer />
          <LabelLegend />
        </div>
      </header>

      <Section
        title="Ask the prospectus"
        intro="Questions are answered from this document only, with page references."
      >
        <AskBox documentId={id} />
      </Section>

      <OfferSection documentId={id} facts={issue} />
      <FinancialsSection documentId={id} figures={financials.figures} />
      <RatiosSection documentId={id} metrics={financials.metrics} />
      <RisksSection documentId={id} risks={risks} />

      <footer className="mt-12 border-t border-hairline pt-6 text-xs text-muted">
        Every figure links to the PDF page it was read from (p.N = page N in a PDF viewer, which can
        differ from the number printed on the page). Calculated metrics are computed in Python from
        those figures. Nothing on this page predicts listing gains or GMP.
      </footer>
    </main>
  );
}

function basisName(basis: string): string {
  if (basis === "restated_consolidated") return "restated consolidated";
  if (basis === "standalone") return "restated standalone";
  return "basis not stated";
}

function Section({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-14">
      <h2 className="text-2xl text-ink">{title}</h2>
      {intro && <p className="mt-1 text-sm text-muted">{intro}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function factValue(fact: IssueFact): string {
  if (fact.field.endsWith("_date")) return formatDate(fact.value_text);
  if (fact.value_number === null) return fact.value_text;
  if (fact.value_text === "Not applicable") return "Not applicable";
  const unit = fact.unit ?? "";
  if (unit === "equity shares") return `${formatNumber(fact.value_number, "")} shares`;
  if (unit === "INR per share") return `₹${formatNumber(fact.value_number, "")} per share`;
  return `₹${formatNumber(fact.value_number, "")} ${unit.replace("INR ", "")}`;
}

function OfferSection({ documentId, facts }: { documentId: number; facts: IssueFact[] }) {
  const byField = new Map(facts.map((f) => [f.field, f]));
  const sellers = facts.filter((f) => f.field === "offer_for_sale_by");
  const objects = facts.filter((f) => f.field === "use_of_proceeds");
  const key = KEY_FACTS.map((field) => byField.get(field)).filter((f): f is IssueFact => !!f);

  return (
    <Section
      title="The offer"
      intro="As printed in the prospectus. “[●]” means the document leaves it to be filled in later, usually in a price band addendum."
    >
      <dl className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-2 lg:grid-cols-3">
        {key.map((fact) => (
          <div key={fact.field} className="bg-card p-4">
            <dt className="text-xs uppercase tracking-wide text-muted">
              {FIELD_NAMES[fact.field] ?? fact.field}
            </dt>
            <dd className="mt-1 text-base font-medium">
              {factValue(fact)}
              <Citation documentId={documentId} page={fact.page_no} source={fact.source_text} />
            </dd>
          </div>
        ))}
      </dl>

      {sellers.length > 0 && (
        <div className="mt-6">
          <h3 className="text-base text-ink">Selling shareholders</h3>
          <ul className="mt-2 divide-y divide-hairline rounded-lg border border-hairline text-sm">
            {sellers.map((s) => (
              <li key={s.label} className="flex flex-wrap justify-between gap-2 px-4 py-2">
                <span>{s.label}</span>
                <span className="font-medium">
                  up to {factValue(s)}
                  <Citation documentId={documentId} page={s.page_no} source={s.source_text} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {objects.length > 0 && (
        <div className="mt-6">
          <h3 className="text-base text-ink">Use of proceeds</h3>
          <div className="mt-2 overflow-x-auto rounded-lg border border-hairline">
            <table className="w-full text-sm">
              <thead className="bg-paper text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Object</th>
                  <th className="px-4 py-2 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {objects.map((o) => (
                  <tr key={o.label}>
                    <td className="px-4 py-2">{o.label}</td>
                    <td className="whitespace-nowrap px-4 py-2 text-right font-medium tabular-nums">
                      {factValue(o)}
                      <Citation documentId={documentId} page={o.page_no} source={o.source_text} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="mt-3">
        <OutputLabel label="verified fact (from the document)" />
      </div>
    </Section>
  );
}

function FigureTable({
  documentId,
  figures,
  metrics,
  caption,
}: {
  documentId: number;
  figures: Figure[];
  metrics: string[];
  caption: string;
}) {
  const present = metrics.filter((m) => figures.some((f) => f.metric === m));
  if (present.length === 0) return null;
  // The first printed figure for a metric and period is shown, matching the backend
  const cell = new Map<string, Figure>();
  for (const f of figures) {
    const k = `${f.metric}|${f.period}`;
    if (!cell.has(k)) cell.set(k, f);
  }
  const periods = sortPeriods(
    figures.filter((f) => present.includes(f.metric)).map((f) => f.period),
  );
  const unit = figures.find((f) => present.includes(f.metric) && f.unit.startsWith("INR "))?.unit;

  return (
    <div className="overflow-x-auto rounded-lg border border-hairline">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="px-4 pt-3 text-left text-xs text-muted">
          {caption}
          {unit ? ` (${unitCaption(unit)} unless stated)` : ""}
        </caption>
        <thead className="text-xs text-muted">
          <tr className="border-b border-hairline">
            <th className="px-4 py-2 text-left font-medium">Line item</th>
            {periods.map((p) => (
              <th key={p} className="whitespace-nowrap px-4 py-2 text-right font-medium">
                {periodName(p)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline/70">
          {present.map((m) => (
            <tr key={m}>
              <th scope="row" className="px-4 py-2 text-left font-normal">
                {metricName(m)}
                {m.startsWith("eps_") && <span className="text-xs text-muted"> (₹ per share)</span>}
              </th>
              {periods.map((p) => {
                const f = cell.get(`${m}|${p}`);
                return (
                  <td key={p} className="whitespace-nowrap px-4 py-2 text-right tabular-nums">
                    {f ? (
                      <>
                        {formatNumber(f.value, f.unit)}
                        <Citation documentId={documentId} page={f.page_no} source={f.source_text} />
                      </>
                    ) : (
                      <span className="text-muted/70" title="Not printed in this document">
                        –
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FinancialsSection({ documentId, figures }: { documentId: number; figures: Figure[] }) {
  if (figures.length === 0) {
    return (
      <Section title="Financials">
        <p className="text-sm text-muted">No financial statements extracted yet.</p>
      </Section>
    );
  }
  const fiscal = sortPeriods(figures.map((f) => f.period))
    .filter((p) => p.startsWith("FY"))
    .reverse();
  const value = (metric: string, period: string) => {
    const f = figures.find((x) => x.metric === metric && x.period === period);
    return f ? Number(f.value) : null; // for plotting only; no arithmetic
  };
  const data: ChartPoint[] = fiscal.map((p) => ({
    period: p,
    revenue: value("revenue_from_operations", p),
    profit: value("profit_after_tax", p),
  }));
  const unit = figures.find((f) => f.metric === "revenue_from_operations")?.unit ?? "INR million";

  return (
    <Section
      title="Financials"
      intro="Restated figures as printed in the prospectus. A dash means the document does not print that line for that period."
    >
      <FinancialsChart data={data} unit={unitCaption(unit)} />
      <div className="mt-6 flex flex-col gap-6">
        <FigureTable
          documentId={documentId}
          figures={figures}
          metrics={FLOW_METRICS}
          caption="Profit and loss, and cash flow"
        />
        <FigureTable
          documentId={documentId}
          figures={figures}
          metrics={BALANCE_METRICS}
          caption="Balance sheet, as at each date"
        />
      </div>
      <div className="mt-3">
        <OutputLabel label="verified fact (from the document)" />
      </div>
    </Section>
  );
}

function RatiosSection({ documentId, metrics }: { documentId: number; metrics: Metric[] }) {
  if (metrics.length === 0) return null;
  // Balance-sheet metrics are dated "as at"; the rest cover a period. Separate tables keep
  // each one dense instead of interleaving dates and periods as columns.
  const atDate = metrics.filter((m) => m.period.startsWith("as at"));
  const overPeriod = metrics.filter((m) => !m.period.startsWith("as at"));
  return (
    <Section
      title="Calculated metrics"
      intro="Computed in Python from the figures above; hover a name for its formula. Part-year ratios are not annualised. A blank means an input is missing, so nothing was guessed."
    >
      <div className="flex flex-col gap-6">
        <MetricTable
          documentId={documentId}
          metrics={overPeriod}
          caption="Profitability and returns, for each period"
        />
        <MetricTable
          documentId={documentId}
          metrics={atDate}
          caption="Debt and equity, at each date"
        />
      </div>
      <p className="mt-2 text-xs text-muted">
        * Part-year period; not annualised. Page links show where each input was read.
      </p>
      <div className="mt-3">
        <OutputLabel label="calculated metric" />
      </div>
    </Section>
  );
}

function MetricTable({
  documentId,
  metrics,
  caption,
}: {
  documentId: number;
  metrics: Metric[];
  caption: string;
}) {
  if (metrics.length === 0) return null;
  const names = [...new Set(metrics.map((m) => m.metric))];
  const periods = sortPeriods(metrics.map((m) => m.period));
  const cell = new Map(metrics.map((m) => [`${m.metric}|${m.period}`, m]));
  return (
    <div className="overflow-x-auto rounded-lg border border-hairline">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="px-4 pt-3 text-left text-xs text-muted">{caption}</caption>
        <thead className="text-xs text-muted">
          <tr className="border-b border-hairline">
            <th className="px-4 py-2 text-left font-medium">Metric</th>
            {periods.map((p) => (
              <th key={p} className="whitespace-nowrap px-4 py-2 text-right font-medium">
                {periodName(p)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline/70">
          {names.map((name) => {
            const formula = metrics.find((m) => m.metric === name)?.formula;
            return (
              <tr key={name}>
                <th scope="row" className="min-w-[13rem] px-4 py-2 text-left font-normal">
                  <span
                    title={formula}
                    className="cursor-help underline decoration-dotted underline-offset-2"
                  >
                    {metricName(name)}
                  </span>
                </th>
                {periods.map((p) => {
                  const m = cell.get(`${name}|${p}`);
                  return (
                    <td key={p} className="whitespace-nowrap px-4 py-2 text-right tabular-nums">
                      {m ? (
                        <span title={m.note ?? undefined}>
                          {formatNumber(m.value_display ?? m.value, m.unit)}
                          {m.note ? <sup className="text-muted">*</sup> : null}
                          <Citations documentId={documentId} pages={m.input_pages} />
                        </span>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RisksSection({ documentId, risks }: { documentId: number; risks: Risk[] }) {
  if (risks.length === 0) return null;
  const order = Object.keys(CATEGORY_NAMES);
  const groups = order
    .map((category) => ({ category, items: risks.filter((r) => r.category === category) }))
    .filter((g) => g.items.length > 0);
  return (
    <Section
      title={`Risk factors (${risks.length} disclosed)`}
      intro="Headings as disclosed by the company. Categories are assigned by simple keyword rules, not by a person or an AI, and can be wrong; risks no rule matches are left uncategorised rather than guessed."
    >
      <div className="flex flex-wrap gap-2 text-xs">
        {groups.map((g) => (
          <a
            key={g.category}
            href={`#risk-${g.category}`}
            className="rounded-full border border-hairline px-3 py-1 hover:bg-accent-soft"
          >
            {CATEGORY_NAMES[g.category]} · {g.items.length}
          </a>
        ))}
      </div>
      <div className="mt-6 flex flex-col gap-8">
        {groups.map((g) => (
          <div key={g.category} id={`risk-${g.category}`}>
            <h3 className="text-base text-ink">
              {CATEGORY_NAMES[g.category]}{" "}
              <span className="font-normal text-muted">({g.items.length})</span>
            </h3>
            <ol className="mt-2 flex flex-col gap-2">
              {g.items.map((r) => (
                <li
                  key={`${r.number}-${r.page_no}`}
                  className="rounded-lg border border-hairline p-3 text-sm leading-relaxed"
                >
                  <span className="mr-2 font-mono text-xs text-muted">#{r.number}</span>
                  {r.text}
                  <Citation documentId={documentId} page={r.page_no} />
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
      <div className="mt-3">
        <OutputLabel label="company claim (disclosed risk factor)" />
      </div>
    </Section>
  );
}
