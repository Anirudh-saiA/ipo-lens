import { Disclaimer } from "@/components/Disclaimer";
import { IpoTable } from "@/components/Ipo";
import { api, type Ipo, type IpoStatus } from "@/lib/api";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

// Always shown, in this order, even when empty
const SECTIONS: { status: IpoStatus; title: string; empty: string }[] = [
  { status: "open", title: "Ongoing IPOs", empty: "No IPO is open for bids today." },
  {
    status: "upcoming",
    title: "Upcoming IPOs",
    empty: "No upcoming IPO yet. New ones appear when their prospectus is added.",
  },
  { status: "closed", title: "Closed IPOs", empty: "None." },
];

export default async function Home() {
  let ipos: Ipo[] = [];
  let unavailable = false;
  try {
    ipos = await api.ipos();
  } catch {
    unavailable = true;
  }
  const asOf = ipos[0]?.as_of;

  return (
    <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <header className="max-w-2xl">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-gold">IPO Lens</p>
        <h1 className="mt-2 text-3xl text-ink sm:text-4xl">Indian IPOs, side by side</h1>
        <p className="mt-3 text-muted">
          Revenue, growth, EBITDA, profit and debt for each IPO, read from its prospectus. Every
          number links to its page.
        </p>
        <div className="mt-4">
          <Disclaimer />
        </div>
      </header>

      {unavailable ? (
        <p role="alert" className="mt-10 rounded-lg border border-hairline bg-card p-4 text-sm">
          Data unavailable: the IPO Lens API is not reachable right now.
        </p>
      ) : (
        SECTIONS.map(({ status, title, empty }) => {
          const items = ipos.filter((i) => i.status === status);
          return (
            <section key={status} className="mt-10">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="text-2xl text-ink">{title}</h2>
                <span className="text-sm text-muted">{items.length}</span>
              </div>
              {items.length === 0 ? (
                <p className="rounded-xl border border-dashed border-hairline px-4 py-6 text-sm text-muted">
                  {empty}
                </p>
              ) : (
                <IpoTable ipos={items} />
              )}
            </section>
          );
        })
      )}

      <footer className="mt-12 border-t border-hairline pt-5 text-xs leading-relaxed text-muted">
        Latest fiscal year shown (FY2026), in each company&apos;s own unit: ₹ million, or ₹ lakh
        where the prospectus prints lakh, so compare growth, margins and debt rather than raw
        amounts. Growth, EBITDA and debt / equity are calculated in Python from the restated
        statements. Status comes from the printed bid dates
        {asOf ? `, as of ${formatDate(asOf)}` : ""}. IPO Lens does not rank IPOs, predict listing
        gains or GMP, or say which is better to invest in.
      </footer>
    </main>
  );
}
