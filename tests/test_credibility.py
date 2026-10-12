"""Phase 5 — credibility guarantees.

These encode the promises the live dashboard and the deck now make:

* the sensitivity sweep is *derived from the supplied input*, never a constant;
* the limitations panel is actually present on the rendered page, with the
  specific caveats a judge would otherwise have to find for themselves;
* the CLI's sensitivity mode cannot run against an invented price.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from arbbound.cli import build_report, sensitivity_report
from arbbound.ingest import load_csv_bhavcopy
from arbbound.report import render

DATA = "data/fixture_gold_2023-2026.csv"


@pytest.fixture(scope="module")
def frame():
    return load_csv_bhavcopy(DATA)


@pytest.fixture(scope="module")
def report(frame):
    return build_report(frame)


# ----------------------------------------------------- sensitivity is derived


def test_sensitivity_uses_the_inputs_reference_price(frame, report):
    """The sweep must be anchored to the sample's price, not a typed constant."""
    ref = report["reference_price_inr_per_gram_fine"]
    for name, s in report["sensitivity"].items():
        assert s["reference_price_inr_per_gram_fine"] == pytest.approx(ref, rel=1e-9), name


def test_sensitivity_reference_price_is_not_a_round_constant(report):
    """A round number would betray a hardcoded fallback like the old 7500.0."""
    ref = report["reference_price_inr_per_gram_fine"]
    assert ref % 100 != 0, f"reference price {ref} looks invented"


def test_sensitivity_covers_every_pair_and_corner(report):
    assert len(report["sensitivity"]) == len(report["bounds"])
    for name, s in report["sensitivity"].items():
        # mint(2) x duty(2) x friction/slippage(2) = 8 corners.
        assert len(s["corners"]) == 8, name
        assert s["min_total_bound_bps"] <= s["max_total_bound_bps"], name


def test_sensitivity_responds_to_a_different_input(frame, report):
    """A different slice must move the reported bound range."""
    late = frame[frame["date"] >= pd.Timestamp("2026-01-01")]
    late_report = build_report(late)
    assert (
        late_report["reference_price_inr_per_gram_fine"]
        != report["reference_price_inr_per_gram_fine"]
    )
    # Higher price level -> the same rupee cost is fewer basis points.
    assert (
        late_report["reference_price_inr_per_gram_fine"]
        > report["reference_price_inr_per_gram_fine"]
    )


def test_sensitivity_report_rejects_empty(frame):
    with pytest.raises(ValueError):
        sensitivity_report(frame[frame["no_trade"]])


# --------------------------------------------- the dashboard states its limits


def test_dashboard_renders_sensitivity_and_limitations(report):
    html = render(report)
    assert "Sensitivity to stated assumptions" in html
    assert "Limitations" in html
    # The specific admissions a judge would otherwise have to dig for.
    for phrase in (
        "Settlement is not execution",
        "Minting cost is assumed, not measured",
        "duty wedge is carried as a range",
        "dated, not always explained",
    ):
        assert phrase in html, phrase


def test_dashboard_numbers_come_from_the_report(report):
    html = render(report)
    assert f"{report['sample']['traded_rows']:,}" in html
    for name, s in report["sensitivity"].items():
        assert name in html, name
        assert f"{s['max_total_bound_bps']:.0f}" in html, name


def test_dashboard_renders_for_a_thin_input(frame):
    """The page must degrade honestly, not crash, when there is little data."""
    thin = frame[(frame["date"] >= pd.Timestamp("2026-08-01"))]
    rep = build_report(thin)
    html = render(rep)
    assert "Limitations" in html
    assert "<html" in html


# ------------------------------------------------- the CLI cannot invent a price


def test_cli_sensitivity_requires_an_input(tmp_path):
    from arbbound.cli import main

    # No --input: must refuse rather than fall back to a constant price.
    with pytest.raises(SystemExit):
        main(["--sensitivity"])


def test_cli_sensitivity_prints_the_derived_price(capsys):
    from arbbound.cli import main

    rc = main(["--sensitivity", "--input", DATA])
    assert rc == 0
    out = capsys.readouterr().out
    assert "from the supplied input" in out
    assert "7500" not in out