from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingest import _clean, ingest_pdf, parse_pdf
from app.main import app
from app.models import Page, PageTable

EXPECTED_TABLE = [
    ["Particulars", "FY2026", "FY2025"],
    ["Revenue from operations", "1,234.56", "987.65"],
    ["Restated profit for the year", "(12.34)", "45.67"],
]


def test_parse_keeps_page_numbers_and_tables(sample_pdf: Path) -> None:
    page_count, pages = parse_pdf(sample_pdf)
    parsed = list(pages)
    assert page_count == 3
    assert [p.page_no for p in parsed] == [1, 2, 3]
    assert "Sample Red Herring Prospectus" in parsed[0].text
    assert parsed[0].tables == []
    assert len(parsed[1].tables) == 1
    assert parsed[1].tables[0].rows == EXPECTED_TABLE
    assert parsed[2].text == ""


def test_clean_strips_nul_and_whitespace() -> None:
    assert _clean(" a\x00b \n") == "ab"
    assert _clean(None) is None


@pytest.mark.db
def test_ingest_stores_every_page_and_table(sample_pdf: Path, db_session: Session) -> None:
    result = ingest_pdf(db_session, sample_pdf, company="Sample Ltd", doc_type="RHP")
    assert (result.page_count, result.table_count, result.already_present) == (3, 1, False)
    pages = db_session.scalar(
        select(func.count()).select_from(Page).where(Page.document_id == result.document_id)
    )
    assert pages == 3
    table = db_session.scalar(select(PageTable).where(PageTable.document_id == result.document_id))
    assert table is not None
    assert (table.page_no, table.rows) == (2, EXPECTED_TABLE)


@pytest.mark.db
def test_ingest_is_idempotent(sample_pdf: Path, db_session: Session) -> None:
    first = ingest_pdf(db_session, sample_pdf, company="Sample Ltd", doc_type="RHP")
    second = ingest_pdf(db_session, sample_pdf, company="Sample Ltd", doc_type="RHP")
    assert second.already_present
    assert second.document_id == first.document_id
    assert second.table_count == 1


def test_ingest_rejects_unknown_doc_type(sample_pdf: Path) -> None:
    with pytest.raises(ValueError, match="doc_type"):
        ingest_pdf(None, sample_pdf, company="X", doc_type="brochure")  # type: ignore[arg-type]


@pytest.mark.db
def test_page_endpoint_returns_text_and_tables(sample_pdf: Path, db_session: Session) -> None:
    result = ingest_pdf(db_session, sample_pdf, company="Sample Ltd", doc_type="RHP")
    client = TestClient(app)

    body = client.get(f"/documents/{result.document_id}/pages/2").json()
    assert body["page_no"] == 2
    assert "restated financial information" in body["text"]
    assert body["tables"][0]["rows"] == EXPECTED_TABLE

    assert client.get(f"/documents/{result.document_id}").json()["page_count"] == 3
    assert client.get(f"/documents/{result.document_id}/pages/4").status_code == 404
    assert client.get("/documents/999999").status_code == 404


@pytest.mark.db
def test_issue_and_risk_endpoints(sample_pdf: Path, db_session: Session) -> None:
    from app.models import IssueFact, Risk

    result = ingest_pdf(db_session, sample_pdf, company="Sample Ltd", doc_type="RHP")
    db_session.add(
        IssueFact(
            document_id=result.document_id,
            page_no=1,
            field="fresh_issue_amount",
            value_text="1,830.57",
            unit="INR million",
            source_text="x",
            extraction_method="t",
        )
    )
    db_session.add(
        Risk(
            document_id=result.document_id,
            page_no=2,
            number=1,
            text="We depend on one supplier.",
            category="operational",
            category_method="keyword rules v1",
            origin="disclosed",
        )
    )
    db_session.commit()
    client = TestClient(app)
    (fact,) = client.get(f"/documents/{result.document_id}/issue").json()
    assert (fact["page_no"], fact["output_label"]) == (1, "verified fact (from the document)")
    (risk,) = client.get(f"/documents/{result.document_id}/risks").json()
    assert (risk["number"], risk["page_no"], risk["category_method"]) == (1, 2, "keyword rules v1")
