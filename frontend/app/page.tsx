import { Disclaimer } from "@/components/Disclaimer";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">IPO Lens</h1>
      <p className="text-lg text-neutral-600 dark:text-neutral-300">
        Understand an IPO beyond the hype.
      </p>
      <p className="text-neutral-600 dark:text-neutral-300">
        Cited, calculated research on Indian IPO prospectuses. Every figure links to its source
        page.
      </p>
      <Disclaimer />
    </main>
  );
}
