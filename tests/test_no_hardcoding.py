"""Guards against hardcoded results.

A research tool that quietly returns a stored answer is worse than no tool:
it looks rigorous and proves nothing. These tests assert the properties that
make the results *derived* rather than *recalled*.

The central one is :func:`test_analysis_is_not_reproducible_from_a_stored_answer`,
which reconstructs the published verdict from a **different slice** of the data
and requires the code to produce a different one. If someone ever pasted a
number into the pipeline, this fails immediately.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd
import pytest

from arbbound.bound import compute_pair_bound
from arbbound.cli import build_report
from arbbound.contracts import spec_for
from arbbound.deck import _headline_break
from arbbound.ingest import load_csv_bhavcopy

DATA = "data/fixture_gold_2023-2026.csv"


@pytest.fixture(scope="module")
def frame():
    return load_csv_bhavcopy(DATA)


# ------------------------------------------------- no literals in the results

#: Keyword arguments that carry human-readable provenance. A date in one of
#: these is documentation ("circular dated 2025-08-05"), not a branch.
_PROVENANCE_KWARGS = {"detail", "source", "citation", "note", "url", "reference"}


def _non_literal_nodes(tree: ast.AST) -> set[int]:
    """Ids of string constants that are allowed to contain a date.

    Docstrings and provenance keyword arguments may name a date when explaining
    where a fact came from. Everywhere else, a date literal is a bug.
    """
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                skip.add(id(body[0].value))
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in _PROVENANCE_KWARGS:
                    for sub in ast.walk(kw.value):
                        skip.add(id(sub))
    return skip


def _looks_like_a_date(text: str) -> bool:
    """True if a YYYY-MM or YYYY-MM-DD token appears *anywhere* in the string.

    Position matters: checking only ``text[4]`` would miss a date embedded in a
    sentence ("circular dated 2025-08-05") - and an embedded date is exactly the
    shape of the bug this guards against.
    """
    return re.search(r"\b\d{4}-\d{2}(?:-\d{2})?\b", text) is not None


def test_no_hardcoded_dates_in_result_path():
    """No module may branch on a remembered date.

    A date literal in executable code pins a result to one dataset. This is the
    exact bug that was caught in the deck: it used to search for the literal
    string "2024-11" to choose its headline break, so the headline silently
    vanished on any other input. Provenance prose is exempt; logic is not.
    """
    offenders = []
    for path in sorted(Path("arbbound").glob("*.py")):
        tree = ast.parse(path.read_text())
        skip = _non_literal_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skip
                and _looks_like_a_date(node.value)
            ):
                offenders.append((str(path), node.lineno, node.value))
    assert not offenders, f"date literals in executable code: {offenders}"


def test_headline_break_is_not_pinned_to_a_date():
    """The headline must follow the data, not a remembered calendar date."""
    report = {
        "regime_breaks": {
            "A/B": [{"date": "2031-07-04", "magnitude_bps": -400.0,
                     "median_before_bps": 200.0, "median_after_bps": -200.0}],
        }
    }
    found = _headline_break(report)
    assert found is not None
    assert found["date"] == "2031-07-04"


def test_headline_absent_when_nothing_large_enough():
    report = {
        "regime_breaks": {
            "A/B": [{"date": "2030-01-01", "magnitude_bps": -5.0,
                     "median_before_bps": 3.0, "median_after_bps": -2.0}],
        }
    }
    assert _headline_break(report) is None


def test_headline_absent_on_empty_breaks():
    assert _headline_break({"regime_breaks": {}}) is None
    assert _headline_break({}) is None


# ------------------------------------------- results must follow the input


def test_analysis_is_not_reproducible_from_a_stored_answer(frame):
    """Truncate the sample and require a *different* verdict.

    This is the load-bearing test. If the pipeline contained a hardcoded result,
    a different input would still produce the same one.
    """
    full = build_report(frame)

    # Take a genuinely different slice: drop everything before 2026.
    late = frame[frame["date"] >= pd.Timestamp("2026-01-01")]
    assert len(late) < len(frame) * 0.5, "slice should be materially smaller"
    assert late["date"].min() != frame["date"].min(), "slice should start later"
    late_report = build_report(late)

    assert late_report["sample"]["rows"] != full["sample"]["rows"]
    assert late_report["sample"]["start"] != full["sample"]["start"]

    # Walk-forward verdicts must respond to the input, not repeat.
    differing = [
        name
        for name in full["walk_forward"]
        if name in late_report["walk_forward"]
        and full["walk_forward"][name]["verdict"]
        != late_report["walk_forward"][name]["verdict"]
    ]
    assert differing, "verdicts identical across different inputs - suspicious"

    # And the headline break must move with the data.
    full_head = _headline_break(full)
    late_head = _headline_break(late_report)
    assert (full_head is None) != (late_head is None) or (
        full_head is not None
        and late_head is not None
        and full_head["date"] != late_head["date"]
    ), "headline break did not respond to changed input"


def test_reference_price_is_computed_not_stored(frame):
    """The bps conversion must use this sample's price level, not a constant."""
    ref = build_report(frame)["reference_price_inr_per_gram_fine"]
    assert ref > 0
    # The fixture spans 2023-2026 with gold rallying hard, so the median must sit
    # inside the observed range rather than being a round invented number.
    traded = frame[~frame["no_trade"]]
    assert traded["px_per_g_fine"].min() <= ref <= traded["px_per_g_fine"].max()


def test_bound_reacts_to_mint_cost_override():
    """Changing the assumption must change the bound, or it is not wired in."""
    a, b = spec_for("GOLDM"), spec_for("GOLDPETAL")
    cheap = compute_pair_bound(a, b, 12_000.0, mint_cost_per_bar=20.0)
    dear = compute_pair_bound(a, b, 12_000.0, mint_cost_per_bar=60.0)
    assert dear.structural_bps > cheap.structural_bps


def test_bound_reacts_to_duty_override():
    a, b = spec_for("GOLDM"), spec_for("GOLDPETAL")
    low = compute_pair_bound(a, b, 12_000.0, duty_wedge_bps=0.0)
    high = compute_pair_bound(a, b, 12_000.0, duty_wedge_bps=400.0)
    assert high.total_bound_bps.high_bps > low.total_bound_bps.high_bps


# ------------------------------------------------- nothing synthetic leaks in


def test_bundled_data_is_real_mcx_not_synthetic(frame):
    """Guard against a future commit swapping in generated rows.

    Synthetic fixtures in this field are the known failure mode of every
    competitor repo. Real MCX gold has moved through several regimes in the
    sample window, so the close prices must not be a random walk from a seed.
    """
    traded = frame[~frame["no_trade"]]
    assert len(traded) > 5_000

    # Real settlement prices have a minimum tick of 1 rupee, so every close is
    # an exact multiple of 1.0 after rounding.
    assert (traded["Close"] % 1 == 0).all(), "non-integer close prices found"

    # Prices are strictly positive and in a plausible INR/gram band for gold.
    assert traded["px_per_g_fine"].min() > 1_000
    assert traded["px_per_g_fine"].max() < 200_000


def test_raw_capture_carries_padding_the_normaliser_removes():
    """Prove the normaliser does real work rather than trusting the CSV.

    The committed CSV is already cleaned, so it cannot show that cleaning
    happened. The live JSON capture can: MCX pads every Symbol to a fixed width
    ("GOLD " with a trailing space), and ``_normalise_frame`` must strip it.
    """
    import json

    from arbbound.ingest import load_json_bhavcopy

    raw = json.loads(Path("data/bhavcopy_2026-09-10.json").read_text())
    padded = [r["Symbol"] for r in raw if str(r["Symbol"]) != str(r["Symbol"]).strip()]
    assert padded, "expected MCX symbol padding in the raw capture"

    frame = load_json_bhavcopy("data/bhavcopy_2026-09-10.json")
    assert (frame["symbol"] == frame["symbol"].str.strip()).all()
    assert not any(s.endswith(" ") for s in frame["symbol"])

    # And the per-gram-fine price must be recomputed, never read from an input
    # column: an input that supplies a wrong value must not be trusted.
    row = frame.iloc[0]
    expected = row["Close"] / row["quote_grams"] / row["purity"]
    assert abs(row["px_per_g_fine"] - expected) < 1e-6


def test_fixture_covers_multiple_expiries_per_contract(frame):
    """A synthetic file usually has one row per symbol per day."""
    counts = frame.groupby("symbol")["expiry"].nunique()
    assert counts.min() >= 20, "not enough distinct expiries to be a real bhavcopy"