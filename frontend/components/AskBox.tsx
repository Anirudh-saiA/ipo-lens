"use client";

import { useState } from "react";

import { Citation } from "@/components/Citation";
import { OutputLabel } from "@/components/OutputLabel";
import type { OutputLabel as OutputLabelName } from "@/lib/api";

interface AnswerResponse {
  answer: string;
  pages: number[];
  abstained: boolean;
  model: string | null;
  output_label?: OutputLabelName;
  detail?: string;
}

/** Ask a question of one prospectus. Answers come only from its pages, with citations. */
export function AskBox({ documentId }: { documentId: number }) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    if (question.trim().length < 3 || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(`/api/ask/${documentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const data = (await response.json()) as AnswerResponse;
      if (!response.ok) setError(data.detail ?? "Something went wrong.");
      else setResult(data);
    } catch {
      setError("Could not reach IPO Lens.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-hairline p-4">
      <form onSubmit={ask} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="question" className="sr-only">
          Question about this prospectus
        </label>
        <input
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          placeholder="e.g. Who is the registrar to the issue?"
          className="min-w-0 flex-1 rounded-md border border-hairline bg-transparent px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length < 3}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Reading the prospectus…" : "Ask"}
        </button>
      </form>
      <p className="mt-2 text-xs text-muted">
        Figures and dates are read straight from the verified data, with their page. Other questions
        are answered by a small local AI model from retrieved pages only, so they can take up to a
        minute and may say there is not enough evidence. No advice or predictions.
      </p>
      {error && (
        <p role="alert" className="mt-3 text-sm text-[#9b2c2c]">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-4 rounded-md bg-paper p-3 text-sm" aria-live="polite">
          <p>
            {result.answer}
            {result.pages.map((page) => (
              <Citation key={page} documentId={documentId} page={page} />
            ))}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
            {!result.abstained && result.output_label && (
              <OutputLabel label={result.output_label} />
            )}
            {result.model ? (
              <span>Model: {result.model} (local)</span>
            ) : (
              <span>From verified data</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
