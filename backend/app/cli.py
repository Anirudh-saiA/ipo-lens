"""Command line: python -m app.cli ingest PATH --company NAME --doc-type RHP"""

import argparse
import time
from datetime import date
from pathlib import Path

from app.db import SessionLocal
from app.ingest import ingest_pdf
from app.models import DOC_TYPES


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="store a prospectus PDF page by page")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--company", required=True)
    ingest.add_argument("--doc-type", required=True, choices=DOC_TYPES)
    ingest.add_argument("--filing-date", type=date.fromisoformat, help="YYYY-MM-DD")
    ingest.add_argument("--source-url")

    args = parser.parse_args(argv)
    started = time.perf_counter()
    with SessionLocal() as session:
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


if __name__ == "__main__":
    main()
