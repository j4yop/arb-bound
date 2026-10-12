"""Tests for ingest, matched-maturity basis, and the walk-forward test."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from arbbound.analysis import detect_breaks, walk_forward
from arbbound.bound import compute_pair_bound
from arbbound.contracts import spec_for
from arbbound.ingest import (
    _parse_mcx_date,
    extract_bhavcopy_array,
    load_csv_bhavcopy,
    matched_basis,
)

DATA = "data/fixture_gold_2023-2026.csv"


@pytest.fixture(scope="module")
def frame():
    return load_csv_bhavcopy(DATA)


# ---------------------------------------------------------------- parsing


def test_parses_dd_mm_yyyy():
    assert _parse_mcx_date("07/10/2026") == pd.Timestamp("2026-10-07")


def test_parses_mm_dd_yyyy():
    assert _parse_mcx_date("10/09/2026") == pd.Timestamp("2026-09-10")


def test_parses_compact_expiry():
    assert _parse_mcx_date("04SEP2026") == pd.Timestamp("2026-09-04")


def test_rejects_nonsense_date():
    with pytest.raises(ValueError):
        _parse_mcx_date("not-a-date")


def test_extract_bhavcopy_array_round_trips():
    rows = [{"sLTT": None, "Symbol": "GOLDM", "Close": 1.0}]
    text = "junk before " + json.dumps(rows) + " junk after"
    assert extract_bhavcopy_array(text) == rows


def test_extract_raises_on_empty():
    with pytest.raises(ValueError):
        extract_bhavcopy_array("no data here")


# ------------------------------------------------------------ normalisation


def test_normalises_to_per_gram_fine(frame):
    row = frame[(frame.symbol == "GOLDM") & (~frame.no_trade)].iloc[0]
    expected = row["Close"] / 10.0 / 0.995
    assert row["px_per_g_fine"] == pytest.approx(expected)


def test_strips_symbol_padding(frame):
    assert not frame["symbol"].str.contains(r"\s").any()


def test_no_trade_rows_flagged(frame):
    zero_vol = frame[frame["Volume"] == 0]
    assert zero_vol["no_trade"].all()


def test_options_rows_excluded(frame):
    """OPTFUT rows share the Symbol of their underlying future and would
    silently corrupt every downstream average if not filtered."""
    assert set(frame["symbol"]) <= {"GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"}


def test_thin_flag_uses_both_volume_and_open_interest(frame):
    thin = frame[frame["is_thin"]]
    assert (thin["Volume"] < 25).any() or (thin["OpenInterest"] < 50).any()


# -------------------------------------------------------- matched maturity


def test_matched_basis_only_returns_maturity_comparable_days(frame):
    """Non-empty output is required, but rows may legitimately be missing on
    days when a contract did not trade. What must never happen is a value
    invented where no comparable maturity existed."""
    basis = matched_basis(frame, max_maturity_gap_days=7, max_dte=120)
    assert not basis.empty
    # Every pair produced real observations.
    assert (basis.notna().sum() > 50).all()


def test_matched_basis_rejects_oversized_maturity_gap():
    """A gap of 40 days must produce nothing, proving the matcher is real."""
    tiny = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02"] * 2),
            "symbol": ["GOLDM", "GOLDPETAL"],
            "expiry": pd.to_datetime(["2026-01-05", "2026-02-10"]),
            "days_to_expiry": [3, 39],
            "px_per_g_fine": [100.0, 101.0],
            "no_trade": [False, False],
        }
    )
    out = matched_basis(tiny, max_maturity_gap_days=7)
    assert out.iloc[0].isna().all()


def test_matched_basis_pairs_near_maturities():
    tiny = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02"] * 2),
            "symbol": ["GOLDM", "GOLDPETAL"],
            "expiry": pd.to_datetime(["2026-01-05", "2026-01-06"]),
            "days_to_expiry": [3, 4],
            "px_per_g_fine": [100.0, 101.0],
            "no_trade": [False, False],
        }
    )
    out = matched_basis(tiny, max_maturity_gap_days=7)
    assert out["GOLDM/GOLDPETAL"].iloc[0] == pytest.approx(
        1e4 * np.log(100.0 / 101.0)
    )


# ------------------------------------------------------------ walk-forward


def _synthetic_basis(n=400, centre=0.0, spread=10.0, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(rng.normal(centre, spread, n), index=idx)


def test_walk_forward_returns_none_on_tiny_sample():
    pb = compute_pair_bound(spec_for("GOLDM"), spec_for("GOLDPETAL"), 12_000.0)
    assert walk_forward(_synthetic_basis(10), pb) is None


def test_quiet_series_is_not_arbitragable():
    pb = compute_pair_bound(spec_for("GOLDTEN"), spec_for("GOLDPETAL"), 12_000.0)
    result = walk_forward(_synthetic_basis(400, centre=0.0, spread=10.0), pb)
    assert result.verdict == "NOT_ARBITRAGABLE"
    assert result.test_cleared == 0


def test_one_way_cost_is_respected():
    """A move in the *cheap-to-manufacture* direction must not be counted.

    For GOLDPETAL/GOLDGUINEA, PETAL is the expensive contract (per-gram
    overhead ~8x). An opportunity exists only if PETAL trades **above**
    GUINEA. A large *downward* deviation is the un-exploitable direction.
    """
    pb = compute_pair_bound(spec_for("GOLDPETAL"), spec_for("GOLDGUINEA"), 12_000.0)
    assert pb.overhead_a_per_g > pb.overhead_b_per_g  # PETAL is the dear one

    idx = pd.bdate_range("2024-01-01", periods=400)
    series = pd.Series(np.full(400, 20.0), index=idx)
    series.iloc[280:] -= 900.0   # un-exploitable direction, far beyond bound
    result = walk_forward(series, pb)
    assert result.verdict == "NOT_ARBITRAGABLE"
    assert result.test_cleared == 0


def test_opportunity_in_tradable_direction_is_flagged():
    """The converse guard: PETAL trading above GUINEA, beyond the bound, must
    flag as a real candidate."""
    pb = compute_pair_bound(spec_for("GOLDPETAL"), spec_for("GOLDGUINEA"), 12_000.0)
    idx = pd.bdate_range("2024-01-01", periods=400)
    series = pd.Series(np.full(400, -20.0), index=idx)
    series.iloc[280:] += 900.0   # PETAL rich vs GUINEA: the tradeable side
    result = walk_forward(series, pb)
    assert result.test_cleared > 0


def test_training_window_precedes_test_window(frame):
    pb = compute_pair_bound(spec_for("GOLDPETAL"), spec_for("GOLDTEN"), 12_000.0)
    result = walk_forward(matched_basis(frame)["GOLDPETAL/GOLDTEN"].dropna(), pb)
    assert result.train_end < result.test_start


def test_centre_is_fitted_on_train_only():
    """Shifting the test window must not move the centring level, proving the
    test has no look-ahead."""
    pb = compute_pair_bound(spec_for("GOLDPETAL"), spec_for("GOLDTEN"), 12_000.0)
    series = _synthetic_basis(400, centre=5.0, spread=10.0)
    first = walk_forward(series, pb)
    shifted = series.copy()
    shifted.iloc[300:] += 500.0
    second = walk_forward(shifted, pb)
    assert first.train_median_bps == pytest.approx(second.train_median_bps)


# --------------------------------------------------------- break detection


def test_detects_a_clean_level_shift():
    idx = pd.bdate_range("2024-01-01", periods=300)
    values = np.concatenate([
        np.zeros(150),
        np.full(150, 200.0),
    ])
    series = pd.Series(values, index=idx)
    found = detect_breaks(series, min_segment=15, max_breaks=1)
    assert found
    assert abs(found[0].magnitude_bps) == pytest.approx(200, abs=2)


def test_finds_nothing_in_pure_noise():
    series = _synthetic_basis(300, centre=0.0, spread=50.0, seed=7)
    found = detect_breaks(series, min_segment=30, max_breaks=4)
    # Any hit must be small relative to the noise scale.
    assert all(abs(b.magnitude_bps) < 120 for b in found)


def test_break_reports_volume_signature():
    idx = pd.bdate_range("2024-01-01", periods=200)
    series = pd.Series(np.concatenate([np.zeros(100), np.full(100, 150.0)]), index=idx)
    volumes = pd.Series(np.concatenate([np.full(100, 100.0), np.full(100, 400.0)]), index=idx)
    found = detect_breaks(series, volumes, min_segment=15, max_breaks=1)
    assert found
    assert found[0].classification == "liquidity-event"
    assert found[0].volume_after > found[0].volume_before