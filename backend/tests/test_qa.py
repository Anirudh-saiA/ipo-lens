"""Q&A guards, with a fake embedder and a scripted model, so no AI model is needed."""

import hashlib
import json
import re
from typing import Literal

import pytest
from sqlalchemy.orm import Session

from app.chunks import split_page
from app.models import Chunk, Document
from app.models_ai import EMBEDDING_DIM
from app.qa import (
    ADVICE_REFUSAL,
    NOT_ENOUGH,
    _parse,
    answer_question,
    is_advice_request,
    numbers_supported,
)


class FakeEmbedder:
    """Bag-of-words hashing: texts sharing words get similar vectors."""

    name = "fake-embedder"

    def embed(self, texts: list[str], kind: Literal["document", "query"]) -> list[list[float]]:
        vectors = []
        for t in texts:
            v = [0.0] * EMBEDDING_DIM
            for word in re.findall(r"[a-z0-9]+", t.lower()):
                v[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIM] += 1.0
            vectors.append(v if any(v) else [1.0] + [0.0] * (EMBEDDING_DIM - 1))
        return vectors


class ScriptedModel:
    name = "scripted"

    def __init__(self, reply: dict[str, object] | str) -> None:
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        return self.reply


def test_split_page_overlaps_and_skips_blank_pages() -> None:
    text = "\n".join(f"Line {i} " + "x" * 60 for i in range(40))
    chunks = split_page(text, size=500, overlap=100)
    assert len(chunks) > 3
    assert all(len(c) <= 500 for c in chunks)
    assert chunks[0][-50:] in text and chunks[1][:20] in chunks[0]  # overlap
    assert split_page("  12  ") == []


@pytest.mark.parametrize(
    "question",
    [
        "Should I apply for this IPO?",
        "What will the listing gain be?",
        "What is the GMP today?",
        "Is it a good investment?",
        "Will the stock list at a premium?",
    ],
)
def test_advice_and_predictions_are_recognised(question: str) -> None:
    assert is_advice_request(question)


@pytest.mark.parametrize(
    "question",
    ["What was revenue from operations in FY2026?", "Who is the registrar to the issue?"],
)
def test_factual_questions_are_not_advice(question: str) -> None:
    assert not is_advice_request(question)


def test_numbers_must_be_printed_on_cited_pages() -> None:
    sources = ["Revenue from operations 12,668.18 for Fiscal 2026"]
    assert numbers_supported("Revenue was ₹12,668.18 million in Fiscal 2026.", sources, "")
    assert not numbers_supported("Revenue grew 20% to ₹12,668.18 million.", sources, "")
    assert numbers_supported("It was 12,668.18 in FY2026.", sources, "What was it in FY2026?")


def test_parse_tolerates_text_around_json() -> None:
    assert _parse('Sure: {"answer": "x", "pages": ["91"]} done') == ("x", [91])
    assert _parse("no json here") is None
    assert _parse('{"answer": 5, "pages": []}') is None


@pytest.fixture
def indexed(db_session: Session) -> int:
    doc = Document(company="Sample Ltd", doc_type="RHP", sha256="b" * 64, page_count=200)
    db_session.add(doc)
    db_session.flush()
    embedder = FakeEmbedder()
    texts = {
        91: "Restated statement of profit and loss. Revenue from operations 12,668.18 Fiscal 2026",
        36: "We are substantially dependent on a single supplier, JSW Steel Coated Products",
        4: "Registrar to the issue: KFin Technologies Limited",
    }
    for page, text in texts.items():
        (vector,) = embedder.embed([text], kind="document")
        db_session.add(Chunk(document_id=doc.id, page_no=page, text=text, embedding=vector))
    db_session.commit()
    return doc.id


@pytest.mark.db
def test_grounded_answer_is_returned_with_its_pages(db_session: Session, indexed: int) -> None:
    model = ScriptedModel({"answer": "It depends on JSW Steel Coated Products.", "pages": [36]})
    a = answer_question(
        db_session, indexed, "Which supplier does the company depend on?", FakeEmbedder(), model
    )
    assert (a.abstained, a.pages, a.output_label) == (False, [36], "AI interpretation")


@pytest.mark.db
def test_invented_number_becomes_a_refusal(db_session: Session, indexed: int) -> None:
    model = ScriptedModel({"answer": "Revenue grew 14% to ₹12,668.18 million.", "pages": [91]})
    a = answer_question(
        db_session, indexed, "Why is the company expanding so fast?", FakeEmbedder(), model
    )
    assert (a.abstained, a.answer) == (True, NOT_ENOUGH)
    assert a.reason == "answer contains a number not printed on the cited pages"


@pytest.mark.db
def test_citing_a_page_that_was_not_retrieved_becomes_a_refusal(
    db_session: Session, indexed: int
) -> None:
    model = ScriptedModel({"answer": "KFin Technologies Limited.", "pages": [999]})
    a = answer_question(db_session, indexed, "Who is the registrar?", FakeEmbedder(), model)
    assert a.abstained and a.reason == "cited pages missing or not among retrieved excerpts"


@pytest.mark.db
def test_model_saying_no_evidence_is_respected(db_session: Session, indexed: int) -> None:
    model = ScriptedModel({"answer": "NOT_ENOUGH_EVIDENCE", "pages": []})
    a = answer_question(db_session, indexed, "What is the CEO's salary?", FakeEmbedder(), model)
    assert a.abstained and a.answer == NOT_ENOUGH


@pytest.mark.db
def test_advice_is_refused_before_the_model_is_called(db_session: Session, indexed: int) -> None:
    model = ScriptedModel({"answer": "Yes, apply.", "pages": [91]})
    a = answer_question(db_session, indexed, "Should I apply for this IPO?", FakeEmbedder(), model)
    assert (a.abstained, a.answer, model.calls) == (True, ADVICE_REFUSAL, 0)


@pytest.mark.db
def test_unparseable_reply_becomes_a_refusal(db_session: Session, indexed: int) -> None:
    a = answer_question(
        db_session, indexed, "Who is the registrar?", FakeEmbedder(), ScriptedModel("I think KFin")
    )
    assert a.abstained and a.reason == "model reply was not valid JSON"


@pytest.mark.db
def test_ask_endpoint_returns_label_and_pages(db_session: Session, indexed: int) -> None:
    from fastapi.testclient import TestClient

    from app.main import app, get_answer_model, get_embedder

    model = ScriptedModel({"answer": "KFin Technologies Limited.", "pages": [4]})
    app.dependency_overrides[get_embedder] = FakeEmbedder
    app.dependency_overrides[get_answer_model] = lambda: model
    try:
        client = TestClient(app)
        body = client.post(f"/documents/{indexed}/ask", json={"question": "Who is the registrar?"})
        assert body.json()["pages"] == [4]
        assert body.json()["output_label"] == "AI interpretation"
        assert client.post("/documents/999999/ask", json={"question": "x y z"}).status_code == 404
        assert client.post(f"/documents/{indexed}/ask", json={"question": ""}).status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.db
def test_breakdown_questions_are_refused_with_page_pointers(
    db_session: Session, indexed: int
) -> None:
    model = ScriptedModel({"answer": "79.56%", "pages": [91]})
    a = answer_question(
        db_session,
        indexed,
        "What percentage of revenue from operations came from North America?",
        FakeEmbedder(),
        model,
    )
    assert a.abstained and a.reason == "breakdown question"
    assert a.pages and "p." in a.answer
    assert model.calls == 0  # the model never sees it
