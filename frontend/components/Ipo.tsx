import Link from "next/link";

import { Citation } from "@/components/Citation";
import { OutputLabel } from "@/components/OutputLabel";
import type { Cited, Ipo, IpoStatus } from "@/lib/api";
import { formatDate, formatNumber, periodName } from "@/lib/format";

const STATUS: Record<IpoStatus, { text: string; style: string }> = {
  open: { text: "Open now", style: "bg-accent text-white" },
  upcoming: { text: "Upcoming", style: "bg-[#f3ead9] text-[#7a5a22]" },
  closed: { text: "Closed", style: "bg-[#efece6] text-muted" },
  unknown: { text: "Dates not printed", style: "bg-[#efece6] text-muted" },
};

export function StatusPill({ status }: { status: IpoStatus }) {
  const s = STATUS[status];
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${s.style}`}>{s.text}</span>
  );
}

export function bidWindow(ipo: Ipo): string | null {
  if (!ipo.bid_open || !ipo.bid_close) return null;
  return `${formatDate(ipo.bid_open.value)} – ${formatDate(ipo.bid_close.value)}`;
}

/** The price band, if a document we hold prints it. RHPs print it as "[●]"; the actual
 *  band appears later in an addendum or advertisement. */
export function priceBandText(band: Cited | null, status?: IpoStatus): string {
  if (band && !band.value.includes("[●]")) return `₹${band.value.replace(" to ", " – ₹")}`;
  return status === "upcoming" ? "Not yet published" : "Not in documents held";
}

const HEADLINE: { key: "revenue_from_operations" | "ebitda" | "profit_after_tax"; name: string }[] =
  [
    { key: "revenue_from_operations", name: "Revenue" },
    { key: "ebitda", name: "EBITDA" },
    { key: "profit_after_tax", name: "Profit after tax" },
  ];

/** Revenue, EBITDA and profit for the latest fiscal year, set large. */
export function HeadlineFigures({ ipo, size = "lg" }: { ipo: Ipo; size?: "lg" | "md" }) {
  const any = HEADLINE.find((h) => ipo.headline[h.key]);
  if (!any) return <p className="text-sm text-muted">Financial statements not extracted yet.</p>;
  const period = ipo.headline[any.key]?.period;
  const unit = ipo.headline[any.key]?.unit?.replace("INR ", "₹ ") ?? "";
  // Show calculated EBITDA in the same style as the reported figures beside it: when the
  // prospectus prints whole numbers, drop the ".00" (display only; no arithmetic)
  const whole = !ipo.headline.revenue_from_operations?.value.includes(".");
  const shown = (key: string, value: string) =>
    key === "ebitda" && whole ? value.replace(/\.00$/, "") : value;
  return (
    <div>
      <div className={`grid grid-cols-3 ${size === "lg" ? "gap-4 sm:gap-8" : "gap-3"}`}>
        {HEADLINE.map(({ key, name }) => {
          const fig = ipo.headline[key];
          const negative = fig?.value.startsWith("-");
          return (
            <div key={key}>
              <div className="text-xs uppercase tracking-wider text-muted">{name}</div>
              <div
                className={`figure mt-1 font-serif ${size === "lg" ? "text-2xl sm:text-4xl" : "text-xl sm:text-2xl"} ${negative ? "text-[#9b2c2c]" : "text-ink"}`}
              >
                {fig ? formatNumber(shown(key, fig.value), fig.unit ?? "") : "–"}
              </div>
              {fig && size === "lg" && (
                <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                  <OutputLabel label={fig.label} />
                  <Citation documentId={fig.document_id} page={fig.page_no} />
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-muted">
        {period ? periodName(period) : ""} · {unit}
        {size === "lg" && (
          <>
            . Values in brackets are losses. EBITDA is calculated in Python from the restated
            statements (profit before tax and before one-off exceptional items, plus finance costs
            and depreciation); it comes from the company&apos;s accounts and does not depend on
            market prices or GMP.
          </>
        )}
      </p>
    </div>
  );
}

export function IpoCard({ ipo }: { ipo: Ipo }) {
  const window = bidWindow(ipo);
  return (
    <Link
      href={`/ipo/${ipo.primary_document_id}`}
      className="group block rounded-xl border border-hairline bg-card p-5 transition hover:border-accent/40 hover:shadow-[0_1px_12px_rgba(31,29,26,0.06)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-xl text-ink group-hover:text-accent">{ipo.company}</h3>
        <StatusPill status={ipo.status} />
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
        {window && <span>Bidding {window}</span>}
        <span>Price band: {priceBandText(ipo.price_band, ipo.status)}</span>
      </div>
      <div className="mt-5">
        <HeadlineFigures ipo={ipo} size="md" />
      </div>
    </Link>
  );
}

function num(c: Cited | undefined, suffix = ""): string {
  if (!c) return "–";
  return `${formatNumber(c.value, c.unit ?? "")}${suffix}`;
}

function Cell({ c, suffix = "", loss = false }: { c?: Cited; suffix?: string; loss?: boolean }) {
  const negative = loss && c?.value.startsWith("-");
  return (
    <td
      className={`figure whitespace-nowrap px-3 py-3 text-right ${negative ? "text-[#9b2c2c]" : ""}`}
    >
      {num(c, suffix)}
      {c && <Citation documentId={c.document_id} page={c.page_no} />}
    </td>
  );
}

/** One row per IPO: the same facts side by side. Sorted by bid date, never ranked. */
export function IpoTable({ ipos }: { ipos: Ipo[] }) {
  const unit = ipos[0]?.headline.revenue_from_operations?.unit;
  return (
    <div className="overflow-x-auto rounded-xl border border-hairline bg-card">
      <table className="w-full min-w-[820px] text-sm">
        <thead className="text-xs uppercase tracking-wider text-muted">
          <tr className="border-b border-hairline">
            <th className="px-3 py-3 text-left font-medium">Company</th>
            <th className="px-3 py-3 text-left font-medium">Bidding</th>
            <th className="px-3 py-3 text-right font-medium">Price band</th>
            <th className="px-3 py-3 text-right font-medium">Revenue</th>
            <th className="px-3 py-3 text-right font-medium">Growth</th>
            <th className="px-3 py-3 text-right font-medium">EBITDA</th>
            <th className="px-3 py-3 text-right font-medium">Profit</th>
            <th className="px-3 py-3 text-right font-medium">Debt / equity</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {ipos.map((ipo) => (
            <tr key={ipo.primary_document_id} className="hover:bg-accent-soft/40">
              <td className="min-w-[13rem] px-3 py-3 font-serif text-base">
                <Link
                  href={`/ipo/${ipo.primary_document_id}`}
                  className="text-ink hover:text-accent"
                >
                  {ipo.company}
                </Link>
                <div className="font-sans text-xs text-muted">
                  {ipo.headline.revenue_from_operations?.unit?.replace("INR ", "₹ ") ?? unit}
                </div>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-muted">{bidWindow(ipo) ?? "–"}</td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-muted">
                {priceBandText(ipo.price_band, ipo.status)}
              </td>
              <Cell c={ipo.headline.revenue_from_operations} />
              <Cell c={ipo.headline.revenue_growth_pct} loss />
              <Cell c={ipo.headline.ebitda} loss />
              <Cell c={ipo.headline.profit_after_tax} loss />
              <Cell c={ipo.headline.debt_to_equity} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
