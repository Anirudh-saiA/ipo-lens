"""Compare stored figures and Python-calculated metrics against a hand-verified golden CSV.

A value matches when it equals the golden value exactly. A difference of at most 0.01 is
reported separately as "rounding": prospectus totals are often rounded independently of
their parts, so a sum of rounded parts can differ by a paisa-level amount.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalculatedMetric, ExtractedFigure

ROUNDING = Decimal("0.01")


@dataclass
class Check:
    metric: str
    period: str
    golden: Decimal | None
    found: Decimal | None
    source: str  # "reported", "calculated" or ""
    status: str  # match, rounding, mismatch, missing, not_verified, not_in_scope


def _ours(session: Session, document_id: int) -> dict[tuple[str, str], tuple[Decimal, str]]:
    found: dict[tuple[str, str], tuple[Decimal, str]] = {}
    for f in session.scalars(
        select(ExtractedFigure)
        .where(ExtractedFigure.document_id == document_id)
        .order_by(ExtractedFigure.page_no, ExtractedFigure.id)  # first printed wins
    ):
        found.setdefault((f.metric, f.period), (f.value, "reported"))
    for m in session.scalars(
        select(CalculatedMetric).where(CalculatedMetric.document_id == document_id)
    ):
        found.setdefault((m.metric, m.period), (m.value, "calculated"))
    return found


def compare(session: Session, document_id: int, golden_csv: Path) -> list[Check]:
    ours = _ours(session, document_id)
    checks = []
    with golden_csv.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            metric, period = row["metric"], row["period"]
            if period == "issue":
                checks.append(Check(metric, period, None, None, "", "not_in_scope"))
                continue
            if not row["golden_value"] or row["verified_by"].startswith("NEEDS"):
                checks.append(Check(metric, period, None, None, "", "not_verified"))
                continue
            golden = Decimal(row["golden_value"])
            value, source = ours.get((metric, period), (None, ""))
            if value is None:
                status = "missing"
            elif value == golden:
                status = "match"
            elif abs(value - golden) <= ROUNDING:
                status = "rounding"
            else:
                status = "mismatch"
            checks.append(Check(metric, period, golden, value, source, status))
    return checks


def report(checks: list[Check]) -> str:
    by_metric: dict[str, list[Check]] = defaultdict(list)
    for c in checks:
        by_metric[c.metric].append(c)
    lines = [f"{'metric':36} {'exact':>7} {'+-0.01':>7} {'wrong':>7} {'missing':>8}  unchecked"]
    totals: defaultdict[str, int] = defaultdict(int)
    for metric, items in by_metric.items():
        counts: defaultdict[str, int] = defaultdict(int)
        for c in items:
            counts[c.status] += 1
            totals[c.status] += 1
        checked = counts["match"] + counts["rounding"] + counts["mismatch"] + counts["missing"]
        unchecked = counts["not_verified"] + counts["not_in_scope"]
        exact = f"{counts['match']}/{checked}" if checked else "-"
        lines.append(
            f"{metric:36} {exact:>7} {counts['rounding']:>7} {counts['mismatch']:>7} "
            f"{counts['missing']:>8}  {unchecked or ''}"
        )
    checked = totals["match"] + totals["rounding"] + totals["mismatch"] + totals["missing"]
    lines.append(
        f"\nChecked {checked}: {totals['match']} exact, {totals['rounding']} within 0.01, "
        f"{totals['mismatch']} wrong, {totals['missing']} missing. "
        f"Not yet verified: {totals['not_verified']}. Later milestones: {totals['not_in_scope']}."
    )
    for c in checks:
        if c.status in ("rounding", "mismatch", "missing"):
            lines.append(
                f"  {c.status:9} {c.metric} {c.period}: golden {c.golden}, ours {c.found} "
                f"({c.source or 'not found'})"
            )
    return "\n".join(lines)
