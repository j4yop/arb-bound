"""Regression tests for the live TinyFish ingestion path and MCX date parsing.

The live path is the one that exposed a real defect: MCX's JSON payload carries
both ``Date`` (``MM/DD/YYYY``) and ``DateDisplay`` (``12 Oct 2026``). The parser
tried ``DD/MM/YYYY`` first, so an ambiguous date silently shifted by two months.
``DateDisplay`` is unambiguous, so it must win when present.
"""

from __future__ import annotations

import json

import pytest

from arbbound.ingest import _parse_mcx_date, _normalise_frame

# Minimal but structurally faithful MCX bhavcopy JSON row.
ROW = {
    "sLTT": None,
    "Date": "10/12/2026",  # MM/DD/YYYY per the ingest docstring
    "DateDisplay": "12 Oct 2026",  # unambiguous ground truth
    "Symbol": "GOLDM ",
    "ExpiryDate": "05OCT2026",
    "Open": 100000.0,
    "High": 100500.0,
    "Low": 99500.0,
    "Close": 100100.0,
    "PreviousClose": 99800.0,
    "Volume": 12000,
    "VolumeInThousands": "12.000 KGS ",
    "Value": 5000.0,
    "OpenInterest": 40000,
    "InstrumentName": "FUTCOM",
}


def _rows(**overrides):
    out = []
    for sym, dense in (("GOLDM ", 0.999), ("GOLDGUINEA ", 0.999)):
        row = dict(ROW)
        row["Symbol"] = sym
        if sym == "GOLDGUINEA ":
            row["ExpiryDate"] = "05NOV2026"
        out.append(row)
    return out


# ---------------------------------------------------------------- the defect


def test_date_display_is_not_ambiguous_and_must_win():
    """The live API payload's DateDisplay is unambiguous; Date is MM/DD/YYYY."""
    from pandas import Timestamp

    assert _parse_mcx_date("12 Oct 2026") == Timestamp("2026-10-12")


def test_live_date_is_not_silently_shifted_two_months():
    """Regression: Date '10/12/2026' with DateDisplay '12 Oct 2026' must be
    parsed as 12 October, not 10 December.

    The bug was that _parse_mcx_date tries %d/%m/%Y before %m/%d/%Y, so the
    ambiguous API date resolved the wrong way and every live row moved two
    months. Verified against the real payload captured 2026-10-12.
    """
    import pandas as pd

    frame = _normalise_frame(pd.DataFrame(_rows()))
    assert set(frame["date"].dt.strftime("%Y-%m-%d")) == {"2026-10-12"}, (
        "live rows were dated incorrectly - see DateDisplay in the payload"
    )


def test_dd_mm_yyyy_is_the_documented_first_guess_for_slash_dates():
    """Slash dates stay DD/MM-first, preserving CSV-export behaviour.

    This is deliberately a *guess*: "12/10/2026" is equally valid as DD/MM
    (12 Oct) and MM/DD (12 Dec). The only fix for the live API is DateDisplay,
    which _normalise_frame now prefers. Documented here so nobody mistakes the
    fallback for a resolved format.
    """
    from pandas import Timestamp

    assert _parse_mcx_date("12/10/2026") == Timestamp("2026-10-12")


def test_iso_dates_still_supported():
    from pandas import Timestamp

    assert _parse_mcx_date("2026-10-12") == Timestamp("2026-10-12")


def test_compact_expiry_form_still_supported():
    from pandas import Timestamp

    assert _parse_mcx_date("05OCT2026") == Timestamp("2026-10-05")


# ------------------------------------------------------- the plane's contract


def test_json_extractor_handles_the_live_payload():
    """The project's own extractor, not a reimplementation."""
    from arbbound.ingest import extract_bhavcopy_array

    page = f'garbage before [{{"sLTT":null,"Date":"10/12/2026"}}] trailing'
    rows = extract_bhavcopy_array(page)
    assert rows == [{"sLTT": None, "Date": "10/12/2026"}]


def test_json_extractor_rejects_a_page_with_no_rows():
    from arbbound.ingest import extract_bhavcopy_array

    with pytest.raises(ValueError):
        extract_bhavcopy_array("<html>no bhavcopy here</html>")
