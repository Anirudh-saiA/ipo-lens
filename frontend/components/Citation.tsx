import { API_URL } from "@/lib/api";

/** The page a value comes from. Opens the stored page text so the source can be checked. */
export function Citation({
  documentId,
  page,
  source,
}: {
  documentId: number;
  page: number;
  source?: string;
}) {
  return (
    <a
      href={`${API_URL}/documents/${documentId}/pages/${page}`}
      target="_blank"
      rel="noreferrer"
      title={source ? `PDF page ${page}: ${source}` : `PDF page ${page}`}
      className="ml-1 inline-block rounded px-1 align-baseline text-[11px] font-medium text-sky-700 underline decoration-dotted underline-offset-2 hover:bg-sky-50 dark:text-sky-300 dark:hover:bg-sky-950"
    >
      p.{page}
    </a>
  );
}

/** Pages a calculated metric was computed from. */
export function Citations({ documentId, pages }: { documentId: number; pages: number[] }) {
  return (
    <>
      {pages.map((page) => (
        <Citation key={page} documentId={documentId} page={page} />
      ))}
    </>
  );
}
