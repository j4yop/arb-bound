"""Tests for the contract master and the structural bound.

These encode the economics. If a test here fails, either the contract facts
changed at MCX or the bound logic is wrong - both matter.
"""

from __future__ import annotations

import math

import pytest

from arbbound.bound import (
    DUTY_WEDGE_BPS,
    MINT_COST_PER_BAR_INR,
    PURITY_WEDGE,
    compute_pair_bound,
    fabrication_overhead_per_gram,
)
from arbbound.contracts import CONTRACTS, pairs, spec_for


def test_all_four_gold_contracts_present():
    assert set(CONTRACTS) == {"GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"}


def test_goldm_is_995_and_others_are_999():
    assert spec_for("GOLDM").purity == 0.995
    for sym in ("GOLDTEN", "GOLDGUINEA", "GOLDPETAL"):
        assert spec_for(sym).purity == 0.999


def test_goldm_quotes_per_10g_despite_100g_lot():
    """The classic normalisation trap: lot size is not quote size."""
    m = spec_for("GOLDM")
    assert m.lot_grams == 100
    assert m.quote_grams == 10


def test_spec_for_strips_mcx_padding():
    # MCX pads symbols with trailing spaces in the bhavcopy.
    assert spec_for("GOLDPETAL ") is CONTRACTS["GOLDPETAL"]


def test_fine_grams_per_lot_accounts_for_purity():
    # 100 g at 995 purity is 99.5 g of actual gold.
    assert spec_for("GOLDM").fine_grams_per_lot == pytest.approx(99.5)
    assert spec_for("GOLDPETAL").fine_grams_per_lot == pytest.approx(0.999)


def test_purity_premium_factor_matches_mcx_999_995_rule():
    # MCX circular: proceeds = Rate * 999/995 for 999 delivery into 995 contract.
    assert spec_for("GOLDM").purity_premium_factor == pytest.approx(999 / 995)


def test_pairs_cover_all_six_combinations():
    assert len(pairs()) == 6


# --------------------------------------------------------------- the bound


def test_smaller_bar_has_higher_per_gram_overhead():
    """The core economic claim: overhead is per-bar, so per-gram it scales
    inversely with bar size."""
    overhead = {
        sym: fabrication_overhead_per_gram(spec, 40.0)
        for sym, spec in CONTRACTS.items()
    }
    assert overhead["GOLDPETAL"] > overhead["GOLDGUINEA"] > overhead["GOLDTEN"]
    assert overhead["GOLDTEN"] > overhead["GOLDM"]  # 10 g bar vs 100 g bar
    # PETAL (1 g) is 8x GUINEA (8 g).
    assert overhead["GOLDPETAL"] == pytest.approx(8 * overhead["GOLDGUINEA"])


def test_purity_wedge_is_about_40bps():
    assert PURITY_WEDGE * 1e4 == pytest.approx(40.2, abs=0.1)


def test_bound_includes_purity_wedge_for_mismatched_pairs():
    a = spec_for("GOLDM")        # 995, duty-inclusive
    b = spec_for("GOLDPETAL")    # 999
    pb = compute_pair_bound(a, b, 12_000.0)
    assert pb.purity_mismatch
    assert pb.purity_wedge_bps > 40


def test_no_purity_wedge_between_two_999_contracts():
    a = spec_for("GOLDTEN")
    b = spec_for("GOLDPETAL")
    pb = compute_pair_bound(a, b, 12_000.0)
    assert not pb.purity_mismatch
    # Still has the fabrication component, but no purity wedge.
    assert pb.purity_wedge_bps == pytest.approx(0, abs=1e-6)
    assert pb.structural_bps > 0


def test_bound_band_always_contains_the_low_end():
    a = spec_for("GOLDM")
    b = spec_for("GOLDPETAL")
    pb = compute_pair_bound(a, b, 12_000.0)
    assert pb.total_bound_bps.low_bps < pb.total_bound_bps.high_bps


def test_bound_is_positive_everywhere():
    for a, b in pairs():
        pb = compute_pair_bound(spec_for(a), spec_for(b), 12_000.0)
        assert pb.total_bound_bps.low_bps > 0


def test_higher_reference_price_lowers_bps_bound():
    """Converting a fixed rupee cost to bps must shrink as price rises."""
    a = spec_for("GOLDPETAL")
    b = spec_for("GOLDGUINEA")
    low = compute_pair_bound(a, b, 6_000.0).structural_bps
    high = compute_pair_bound(a, b, 12_000.0).structural_bps
    assert high < low


def test_mint_cost_midpoint_is_within_stated_range():
    mid = 0.5 * (MINT_COST_PER_BAR_INR[0] + MINT_COST_PER_BAR_INR[1])
    assert MINT_COST_PER_BAR_INR[0] <= mid <= MINT_COST_PER_BAR_INR[1]


def test_duty_wedge_is_a_range_not_a_point():
    """The duty is policy-set; the code must never collapse it to a constant."""
    assert DUTY_WEDGE_BPS[0] < DUTY_WEDGE_BPS[1]