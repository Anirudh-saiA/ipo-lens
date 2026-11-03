"""Run the question set and score it.

An answerable question passes when the answer contains the expected value AND at least one
cited page actually prints that value (so the citation is checked against the document,
not against a list someone typed). An unanswerable question passes when the system
abstains.
"""

import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Page
from app.models_ai import AnswerModel, Embedder
from app.qa import Answer, answer_question


@dataclass
class Result:
    document_id: int
    question: str
    answerable: bool
    expected: str
    answer: Answer
    passed: bool
    detail: str
    seconds: float


def _normal(text: str) -> str:
    """Compare ignoring case, spacing, commas and the ₹ sign."""
    return re.sub(r"[\s,₹]", "", text.lower())


def score(
    session: Session, document_id: int, answerable: bool, expected: str, a: Answer
) -> tuple[bool, str]:
    if not answerable:
        return (a.abstained, "abstained" if a.abstained else "answered when it should not")
    if a.abstained:
        return (False, f"abstained ({a.reason})")
    if _normal(expected) not in _normal(a.answer):
        return (False, "expected value not in answer")
    cited = session.scalars(
        select(Page.text).where(Page.document_id == document_id, Page.page_no.in_(a.pages))
    )
    if not any(_normal(expected) in _normal(t) for t in cited):
        return (False, "no cited page prints the expected value")
    return (True, "correct, citation verified")


def evaluate(
    session: Session, eval_csv: Path, embedder: Embedder, model: AnswerModel
) -> list[Result]:
    results = []
    with eval_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            document_id = int(row["document_id"])
            answerable = row["answerable"].strip().upper() == "Y"
            started = time.perf_counter()
            a = answer_question(session, document_id, row["question"], embedder, model)
            passed, detail = score(session, document_id, answerable, row["expected"], a)
            results.append(
                Result(
                    document_id,
                    row["question"],
                    answerable,
                    row["expected"],
                    a,
                    passed,
                    detail,
                    time.perf_counter() - started,
                )
            )
            print(f"  {'PASS' if passed else 'FAIL'}  {row['question'][:70]}  ({detail})")
    return results


def eval_report(results: list[Result], out: Path | None = None) -> str:
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    lines = [
        f"Answerable, answered and cited correctly: "
        f"{sum(r.passed for r in answerable)}/{len(answerable)}",
        f"Unanswerable, refused: {sum(r.passed for r in unanswerable)}/{len(unanswerable)}",
        f"Average time per question: {sum(r.seconds for r in results) / max(len(results), 1):.0f}s",
    ]
    for r in results:
        if not r.passed:
            got = r.answer.answer[:160]
            lines.append(f"  FAIL doc {r.document_id}: {r.question} -> {r.detail}; got: {got}")
    if out is not None:
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "document_id",
                    "question",
                    "answerable",
                    "expected",
                    "passed",
                    "detail",
                    "answer",
                    "pages",
                    "seconds",
                ]
            )
            for r in results:
                w.writerow(
                    [
                        r.document_id,
                        r.question,
                        "Y" if r.answerable else "N",
                        r.expected,
                        "Y" if r.passed else "N",
                        r.detail,
                        r.answer.answer,
                        " ".join(map(str, r.answer.pages)),
                        f"{r.seconds:.1f}",
                    ]
                )
    return "\n".join(lines)
