from decimal import Decimal as D
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.accuracy import compare, report
from app.models import CalculatedMetric, Document, ExtractedFigure

pytestmark = pytest.mark.db

GOLDEN = """metric,period,golden_value,unit,source_page,verified_by,notes
revenue_from_operations,FY2026,12668.18,INR million,91,owner,
profit_after_tax,FY2026,305.39,INR million,91,owner,
total_debt,as at 2026-03-31,3384.55,INR million,401,owner,
other_income,FY2026,30.07,INR million,91,owner,
finance_costs,FY2026,,INR million,91,NEEDS CHECK,
price_band,issue,,INR,1,owner,
"""


def test_compare_classifies_every_row(db_session: Session, tmp_path: Path) -> None:
    doc = Document(company="X", doc_type="RHP", sha256="a" * 64, page_count=1)
    db_session.add(doc)
    db_session.flush()

    def fig(metric: str, value: str) -> ExtractedFigure:
        return ExtractedFigure(
            document_id=doc.id,
            page_no=91,
            metric=metric,
            period="FY2026",
            basis="standalone",
            value=D(value),
            unit="INR million",
            source_text="",
            extraction_method="test",
        )

    db_session.add_all(
        [fig("revenue_from_operations", "12668.18"), fig("profit_after_tax", "305.00")]
    )
    db_session.add(
        CalculatedMetric(
            document_id=doc.id,
            metric="total_debt",
            period="as at 2026-03-31",
            unit="INR million",
            formula="a + b",
            input_figure_ids=[],
            value=D("3384.54"),
        )
    )
    db_session.commit()
    golden = tmp_path / "golden.csv"
    golden.write_text(GOLDEN, encoding="utf-8")

    status = {(c.metric, c.status) for c in compare(db_session, doc.id, golden)}
    assert status == {
        ("revenue_from_operations", "match"),
        ("profit_after_tax", "mismatch"),
        ("total_debt", "rounding"),
        ("other_income", "missing"),
        ("finance_costs", "not_verified"),
        ("price_band", "not_in_scope"),
    }
    text = report(compare(db_session, doc.id, golden))
    assert "Checked 4: 1 exact, 1 within 0.01, 1 wrong, 1 missing." in text
