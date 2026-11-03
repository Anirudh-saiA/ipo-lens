"""Command line.

python -m app.cli ingest PATH --company NAME --doc-type RHP
python -m app.cli financials DOCUMENT_ID
python -m app.cli accuracy DOCUMENT_ID GOLDEN_CSV
python -m app.cli structure DOCUMENT_ID
python -m app.cli index DOCUMENT_ID
python -m app.cli ask DOCUMENT_ID "question"
python -m app.cli qa-eval EVAL_CSV
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from app.accuracy import compare, report
from app.calc import compute_document
from app.chunks import index_document
from app.db import SessionLocal
from app.financials import extract_document
from app.ingest import ingest_pdf
from app.issue import extract_issue
from app.models import DOC_TYPES
from app.models_ai import OllamaAnswerModel, OllamaEmbedder
from app.qa import answer_question
from app.qa_eval import eval_report, evaluate
from app.risks import extract_risks


def main(argv: list[str] | None = None) -> None:
    # Windows consoles default to cp1252, which cannot print ₹
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="store a prospectus PDF page by page")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--company", required=True)
    ingest.add_argument("--doc-type", required=True, choices=DOC_TYPES)
    ingest.add_argument("--filing-date", type=date.fromisoformat, help="YYYY-MM-DD")
    ingest.add_argument("--source-url")

    financials = sub.add_parser(
        "financials", help="extract reported figures, then compute ratios in Python"
    )
    financials.add_argument("document_id", type=int)

    accuracy = sub.add_parser("accuracy", help="compare against a hand-verified golden CSV")
    accuracy.add_argument("document_id", type=int)
    accuracy.add_argument("golden_csv", type=Path)

    structure = sub.add_parser(
        "structure", help="extract offer structure, use of proceeds and risk factors"
    )
    structure.add_argument("document_id", type=int)

    index = sub.add_parser("index", help="split pages into chunks and embed them locally")
    index.add_argument("document_id", type=int)

    ask = sub.add_parser("ask", help="answer a question from the prospectus, with pages")
    ask.add_argument("document_id", type=int)
    ask.add_argument("question")

    qa_eval = sub.add_parser("qa-eval", help="run the question set and report results")
    qa_eval.add_argument("eval_csv", type=Path)
    qa_eval.add_argument("--out", type=Path, help="write per-question results to this CSV")

    args = parser.parse_args(argv)
    started = time.perf_counter()
    with SessionLocal() as session:
        if args.command == "ingest":
            result = ingest_pdf(
                session,
                args.path,
                company=args.company,
                doc_type=args.doc_type,
                filing_date=args.filing_date,
                source_url=args.source_url,
            )
            status = "already stored" if result.already_present else "stored"
            print(
                f"{status}: document {result.document_id}, {result.page_count} pages, "
                f"{result.table_count} tables ({time.perf_counter() - started:.0f}s)"
            )
        elif args.command == "financials":
            figures = extract_document(session, args.document_id)
            metrics = compute_document(session, args.document_id)
            print(f"{len(figures)} reported figures, {len(metrics)} calculated metrics")
        elif args.command == "structure":
            facts = extract_issue(session, args.document_id)
            risks = extract_risks(session, args.document_id)
            print(f"{len(facts)} issue facts, {len(risks)} risk factors")
        elif args.command == "index":
            count = index_document(session, args.document_id, OllamaEmbedder())
            print(f"{count} chunks indexed ({time.perf_counter() - started:.0f}s)")
        elif args.command == "ask":
            answer = answer_question(
                session, args.document_id, args.question, OllamaEmbedder(), OllamaAnswerModel()
            )
            pages = ", ".join(f"p.{p}" for p in answer.pages) or "-"
            print(answer.answer)
            print(f"[{answer.output_label}; pages: {pages}]")
            if answer.reason:
                print(f"(abstained: {answer.reason})")
        elif args.command == "qa-eval":
            results = evaluate(session, args.eval_csv, OllamaEmbedder(), OllamaAnswerModel())
            print(eval_report(results, args.out))
        else:
            print(report(compare(session, args.document_id, args.golden_csv)))


if __name__ == "__main__":
    main()
