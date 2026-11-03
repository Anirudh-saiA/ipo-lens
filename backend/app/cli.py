"""Command line.

python -m app.cli ingest PATH --company NAME --doc-type RHP
python -m app.cli financials DOCUMENT_ID
python -m app.cli accuracy DOCUMENT_ID GOLDEN_CSV
python -m app.cli structure DOCUMENT_ID
"""

import argparse
import time
from datetime import date
from pathlib import Path

from app.accuracy import compare, report
from app.calc import compute_document
from app.db import SessionLocal
from app.financials import extract_document
from app.ingest import ingest_pdf
from app.issue import extract_issue
from app.models import DOC_TYPES
from app.risks import extract_risks


def main(argv: list[str] | None = None) -> None:
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
        else:
            print(report(compare(session, args.document_id, args.golden_csv)))


if __name__ == "__main__":
    main()
