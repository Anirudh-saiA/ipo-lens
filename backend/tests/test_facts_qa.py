"""Figure and date questions are answered from verified data, with the right period."""

from decimal import Decimal as D

import pytest
from sqlalchemy.orm import Session

from app.facts_qa import answer_from_data, detect_intent, detect_period
from app.models import Document, ExtractedFigure, IssueFact


@pytest.mark.parametrize(
    ("question", "key"),
    [
        ("What was the revenue from operations for Fiscal 2026?", "revenue_from_operations"),
        ("What was the restated profit for Fiscal 2025?", "profit_after_tax"),
        ("What was the profit before tax in FY2026?", "profit_before_tax"),
        ("What was the net cash from operating activities?", "net_cash_from_operating_activities"),
        ("What is the EBITDA margin?", "ebitda_margin_pct"),
        ("What is the adjusted EBITDA for FY2026?", "adjusted_ebitda"),
        ("On which date does the bid or issue open?", "bid_open_date"),
        ("On which date does the bid close?", "bid_close_date"),
        ("What is the size of the offer for sale?", "offer_for_sale_amount"),
        ("What is the size of the fresh issue?", "fresh_issue_amount"),
        ("What is the face value of each equity share?", "face_value"),
    ],
)
def test_intent_detection(question: str, key: str) -> None:
    intent = detect_intent(question)
    assert intent is not None and intent[0] == key


def test_text_questions_are_not_claimed() -> None:
    assert detect_intent("Who is the registrar to the issue?") is None
    assert detect_intent("Which supplier does the company depend on?") is None


@pytest.mark.parametrize(
    ("question", "flow"),
    [
        ("revenue for Fiscal 2026", "FY2026"),
        ("revenue in FY2025", "FY2025"),
        ("revenue for the year ended March 31, 2024", "FY2024"),
        ("revenue for the three months ended June 30, 2026", "3M ended 2026-06-30"),
        ("revenue in fiscal 26", "FY2026"),
    ],
)
def test_period_detection(question: str, flow: str) -> None:
    assert detect_period(question)[0] == flow


def test_no_period_means_latest() -> None:
    assert detect_period("what is the revenue") == (None, None)


@pytest.fixture
def doc(db_session: Session) -> int:
    d = Document(company="Sample Ltd", doc_type="RHP", sha256="c" * 64, page_count=100)
    db_session.add(d)
    db_session.flush()

    def fig(metric: str, period: str, value: str, page: int) -> ExtractedFigure:
        return ExtractedFigure(
            document_id=d.id,
            page_no=page,
            metric=metric,
            period=period,
            basis="standalone",
            value=D(value),
            unit="INR million",
            source_text="x",
            extraction_method="t",
        )

    db_session.add_all(
        [
            fig("profit_after_tax", "FY2026", "-455.06", 77),
            fig("profit_after_tax", "3M ended 2026-06-30", "-10.00", 77),
            fig("profit_before_tax", "FY2026", "-375.55", 77),
            IssueFact(
                document_id=d.id,
                page_no=4,
                field="bid_open_date",
                value_text="2026-10-29",
                source_text="x",
                extraction_method="t",
            ),
            IssueFact(
                document_id=d.id,
                page_no=1,
                field="price_band",
                value_text="[●] (not disclosed)",
                source_text="x",
                extraction_method="t",
            ),
        ]
    )
    db_session.commit()
    return d.id


@pytest.mark.db
def test_profit_answer_uses_the_right_line_and_period(db_session: Session, doc: int) -> None:
    a = answer_from_data(db_session, doc, "What was the profit for Fiscal 2026?")
    assert a is not None and a.found and a.pages == [77]
    assert "loss of ₹455.06" in a.answer  # profit after tax, not profit before tax (375.55)
    assert a.output_label == "verified fact (from the document)"


@pytest.mark.db
def test_quarter_is_not_confused_with_the_year(db_session: Session, doc: int) -> None:
    a = answer_from_data(
        db_session, doc, "What was the profit for the three months ended June 30, 2026?"
    )
    assert a is not None and "₹10.00" in a.answer


@pytest.mark.db
def test_missing_period_is_not_guessed(db_session: Session, doc: int) -> None:
    a = answer_from_data(db_session, doc, "What was the profit in Fiscal 2015?")
    assert a is not None and not a.found and a.pages == []
    assert "Not enough evidence" in a.answer


@pytest.mark.db
def test_dates_and_undisclosed_price_band(db_session: Session, doc: int) -> None:
    opens = answer_from_data(db_session, doc, "When does the bid open?")
    assert opens is not None and "October 29, 2026" in opens.answer and opens.pages == [4]
    band = answer_from_data(db_session, doc, "What is the price band?")
    assert band is not None and "not disclosed" in band.answer


@pytest.mark.parametrize(
    ("question", "key"),
    [
        (
            "How much of the net proceeds will be used to repay or prepay borrowings?",
            "use_of_proceeds",
        ),
        ("How many equity shares are offered in the fresh issue?", "fresh_issue_shares"),
        ("How many shares are in the offer for sale?", "offer_for_sale_shares"),
    ],
)
def test_proceeds_and_share_counts_are_not_mistaken_for_other_figures(
    question: str, key: str
) -> None:
    intent = detect_intent(question)
    assert intent is not None and intent[0] == key


def test_breakdown_questions_go_to_the_text_model() -> None:
    assert (
        detect_intent("What percentage of revenue in Fiscal 2026 came from North America?") is None
    )


@pytest.mark.db
def test_repayment_question_returns_only_the_repayment_object(
    db_session: Session, doc: int
) -> None:
    for label, amount in [
        ("Repayment of certain borrowings", "1,250.00"),
        ("Capital equipment", "157.70"),
    ]:
        db_session.add(
            IssueFact(
                document_id=doc,
                page_no=123,
                field="use_of_proceeds",
                label=label,
                value_text=amount,
                value_number=D(amount.replace(",", "")),
                unit="INR million",
                source_text="x",
                extraction_method="t",
            )
        )
    db_session.commit()
    a = answer_from_data(
        db_session, doc, "How much of the net proceeds will be used to repay borrowings?"
    )
    assert a is not None and a.pages == [123]
    assert "1,250.00" in a.answer and "157.70" not in a.answer
