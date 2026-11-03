// Types mirror the FastAPI schemas in backend/app/schemas.py. Numbers arrive as strings
// (Python Decimal) and are kept as strings until display, so nothing is rounded twice.

export type OutputLabel =
  | "verified fact (from the document)"
  | "company claim (disclosed risk factor)"
  | "calculated metric"
  | "AI interpretation";

export interface DocumentSummary {
  id: number;
  company: string;
  doc_type: string;
  filing_date: string | null;
  page_count: number;
}

export interface Figure {
  id: number;
  metric: string;
  period: string;
  basis: string;
  value: string;
  unit: string;
  page_no: number;
  source_text: string;
  output_label: OutputLabel;
}

export interface Metric {
  metric: string;
  period: string;
  value: string;
  unit: string;
  formula: string;
  note: string | null;
  input_pages: number[];
  // Rounded half-up to 2 places by the backend; the browser does no arithmetic
  value_display: string | null;
  output_label: OutputLabel;
}

export interface IssueFact {
  page_no: number;
  field: string;
  label: string | null;
  value_text: string;
  value_number: string | null;
  unit: string | null;
  source_text: string;
  output_label: OutputLabel;
}

export interface Risk {
  number: number | null;
  page_no: number;
  text: string;
  category: string;
  category_method: string | null;
  output_label: OutputLabel;
}

export const API_URL =
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  // Always fresh: prospectus data changes whenever extraction is re-run
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API ${path} returned ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  documents: () => get<DocumentSummary[]>("/documents"),
  document: (id: number) => get<DocumentSummary>(`/documents/${id}`),
  financials: (id: number) =>
    get<{ figures: Figure[]; metrics: Metric[] }>(`/documents/${id}/financials`),
  issue: (id: number) => get<IssueFact[]>(`/documents/${id}/issue`),
  risks: (id: number) => get<Risk[]>(`/documents/${id}/risks`),
};
