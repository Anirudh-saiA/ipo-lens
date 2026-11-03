import { Disclaimer } from "@/components/Disclaimer";
import { IpoCard } from "@/components/Ipo";
import { api, type Ipo, type IpoStatus } from "@/lib/api";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

const SECTIONS: { status: IpoStatus; title: string }[] = [
  { status: "open", title: "Open now" },
  { status: "upcoming", title: "Upcoming" },
  { status: "closed", title: "Recently closed" },
  { status: "unknown", title: "Bid dates not printed" },
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
    <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
      <header className="max-w-2xl">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-gold">IPO Lens</p>
        <h1 className="mt-3 text-4xl text-ink sm:text-5xl">Understand an IPO beyond the hype.</h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          What is inside each Indian IPO prospectus, read and calculated for you, with every figure
          linked to the page it came from.
        </p>
        <div className="mt-6">
          <Disclaimer />
        </div>
      </header>

      {unavailable ? (
        <p role="alert" className="mt-12 rounded-lg border border-hairline bg-card p-4 text-sm">
          Data unavailable: the IPO Lens API is not reachable right now.
        </p>
      ) : (
        <>
          {SECTIONS.filter(({ status }) => status === "open" || status === "upcoming").every(
            ({ status }) => !ipos.some((i) => i.status === status),
          ) && (
            <p className="mt-12 text-sm text-muted">
              No IPO in the library is open or upcoming
              {asOf ? ` as of ${formatDate(asOf)}` : ""}. New prospectuses appear here when added.
            </p>
          )}
          {SECTIONS.map(({ status, title }) => {
            const items = ipos.filter((i) => i.status === status);
            if (items.length === 0) return null;
            return (
              <section key={status} className="mt-14">
                <div className="flex items-baseline justify-between border-b border-hairline pb-2">
                  <h2 className="text-2xl text-ink">{title}</h2>
                  <span className="text-sm text-muted">{items.length}</span>
                </div>
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  {items.map((ipo) => (
                    <IpoCard key={ipo.primary_document_id} ipo={ipo} />
                  ))}
                </div>
              </section>
            );
          })}
        </>
      )}

      <footer className="mt-16 border-t border-hairline pt-6 text-xs leading-relaxed text-muted">
        Status comes from the bid dates printed in each prospectus
        {asOf ? `, as of ${formatDate(asOf)}` : ""}. Prospectuses are from SEBI&apos;s public
        filings. IPO Lens does not predict listing gains or GMP and gives no buy or sell advice.
      </footer>
    </main>
  );
}
