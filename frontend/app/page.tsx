import Link from "next/link";

import { Disclaimer } from "@/components/Disclaimer";
import { api, type DocumentSummary } from "@/lib/api";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Home() {
  let documents: DocumentSummary[] = [];
  let unavailable = false;
  try {
    documents = await api.documents();
  } catch {
    unavailable = true;
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-12 sm:py-16">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">IPO Lens</h1>
        <p className="mt-2 text-lg text-neutral-600 dark:text-neutral-300">
          Understand an IPO beyond the hype.
        </p>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          Cited, calculated research on Indian IPO prospectuses. Every figure links to its source
          page.
        </p>
      </div>
      <Disclaimer />

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Prospectuses
        </h2>
        {unavailable ? (
          <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-300">
            Data unavailable: the IPO Lens API is not reachable. Start it with{" "}
            <code>uvicorn app.main:app</code> from the backend folder.
          </p>
        ) : documents.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-600">No prospectuses ingested yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-neutral-200 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {documents.map((d) => (
              <li key={d.id}>
                <Link
                  href={`/ipo/${d.id}`}
                  className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-900"
                >
                  <span className="font-medium">{d.company}</span>
                  <span className="text-sm text-neutral-500">
                    {d.doc_type}
                    {d.filing_date ? `, ${formatDate(d.filing_date)}` : ""} · {d.page_count} pages
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
