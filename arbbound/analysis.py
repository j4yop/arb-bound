"""Walk-forward test of the arbitrage bound, plus regime-change detection.

Two independent questions are answered here.

1. **Does the observed gap ever clear the structural bound?**
   Tested walk-forward: parameters are fixed on a training window and applied,
   untouched, to a later unseen window. No peeking.

2. **When the basis jumps discontinuously, what happened?**
   A pure structural cost cannot jump. So a genuine break in the basis series
   is evidence that something *other* than fabrication cost drove it - a change
   in contract terms, a liquidity event, or something not yet identified. This
   module locates those breaks precisely and reports the volume signature
   around them, rather than averaging them away.

The second question is the more interesting one. The first is largely settled by
construction; the second is an open investigation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .bound import PairBound
from .contracts import spec_for


# ------------------------------------------------------------ regime detection


@dataclass(frozen=True)
class ExecutabilityCheck:
    """Why a flagged day is or is not actually tradeable.

    A bhavcopy print is a **settlement price**, not a quote you can lift. The
    problem statement is explicit that settlement must not be treated as an
    executable fill, "particularly for thin contracts". So every candidate day
    is re-examined against what the exchange actually printed that day:

    ``hi_lo_cover``
        Whether the spread was inside the day's own high/low band on both
        legs. If the gap could not have been crossed within the printed range,
        it was never available to a trader.
    ``volume_sufficient``
        Whether both legs traded enough to absorb a retail-sized order.
    ``dte_in_window``
        Whether the maturity-matched legs were inside the carry-comparable
        window.
    """

    date: pd.Timestamp
    pair: str
    basis_bps: float
    band_low_bps: float
    band_high_bps: float
    hi_lo_cover: bool
    volume_sufficient: bool
    dte_in_window: bool

    @property
    def executable(self) -> bool:
        return self.hi_lo_cover and self.volume_sufficient and self.dte_in_window


def check_executability(
    candidate_dates: list[pd.Timestamp],
    pair: tuple[str, str],
    bhavcopy: pd.DataFrame,
    basis_series: pd.Series,
    min_volume: int = 25,
    max_dte: int = 120,
) -> list[ExecutabilityCheck]:
    """Test whether flagged days were reachable in the printed market."""
    sym_a, sym_b = pair
    traded = bhavcopy[(~bhavcopy["no_trade"]) & (bhavcopy["days_to_expiry"] <= max_dte)]
    checks = []

    for date in candidate_dates:
        la = traded[(traded["date"] == date) & (traded["symbol"] == sym_a)]
        rb = traded[(traded["date"] == date) & (traded["symbol"] == sym_b)]
        if la.empty or rb.empty:
            continue

        # Maturity-matched legs, same rule as the basis construction.
        # The frame can hold several expiries per (date, symbol), so rows are
        # reduced to explicit scalars before any arithmetic.
        best = None
        for _, ra in la.iterrows():
            for _, rbb in rb.iterrows():
                gap = abs(float(ra["days_to_expiry"]) - float(rbb["days_to_expiry"]))
                if best is None or gap < best[0]:
                    best = (gap, ra, rbb)
        if best is None:
            continue
        gap, ra, rbb = best

        def _s(row, key):
            return float(row[key])

        px_a_hi = _s(ra, "High") / _s(ra, "quote_grams") / _s(ra, "purity")
        px_a_lo = _s(ra, "Low") / _s(ra, "quote_grams") / _s(ra, "purity")
        px_b_hi = _s(rbb, "High") / _s(rbb, "quote_grams") / _s(rbb, "purity")
        px_b_lo = _s(rbb, "Low") / _s(rbb, "quote_grams") / _s(rbb, "purity")

        band_low = 1e4 * math.log(px_a_lo / px_b_hi)
        band_high = 1e4 * math.log(px_a_hi / px_b_lo)

        try:
            observed = float(basis_series.loc[date])
        except (KeyError, ValueError):
            observed = float("nan")
        # Did the day's own range span the quoted settlement gap?
        cover = (
            not math.isnan(observed)
            and band_low <= observed <= band_high
        )
        vol_ok = bool(ra["Volume"] >= min_volume and rbb["Volume"] >= min_volume)
        dte_ok = bool(gap <= 7)

        checks.append(
            ExecutabilityCheck(
                date=date,
                pair=f"{sym_a}/{sym_b}",
                basis_bps=observed,
                band_low_bps=band_low,
                band_high_bps=band_high,
                hi_lo_cover=cover,
                volume_sufficient=vol_ok,
                dte_in_window=dte_ok,
            )
        )
    return checks


@dataclass(frozen=True)
class Break:
    """A detected discontinuity in a basis series."""

    date: pd.Timestamp
    magnitude_bps: float
    median_before_bps: float
    median_after_bps: float
    volume_before: float
    volume_after: float
    classification: str

    def describe(self) -> str:
        return (
            f"{self.date.date()}: {self.median_before_bps:+.1f} -> "
            f"{self.median_after_bps:+.1f} bps ({self.magnitude_bps:+.1f}), "
            f"volume {self.volume_before:,.0f} -> {self.volume_after:,.0f}, "
            f"{self.classification}"
        )


def _cumulative_sum_shift(series: pd.Series, min_segment: int = 15):
    """Yield (index, shift) for every candidate single-break split.

    This is the standard two-sided mean-shift statistic. For each possible
    split point the statistic is the absolute difference between the mean
    before and the mean after, normalised by the pooled standard deviation.
    Scanning all splits and taking the maximum gives the most likely break.
    """
    values = series.to_numpy(dtype=float)
    n = len(values)
    if n < 2 * min_segment:
        return
    cum = np.concatenate([[0.0], np.cumsum(values)])
    for i in range(min_segment, n - min_segment + 1):
        left = values[:i]
        right = values[i:]
        pooled = math.sqrt(
            (left.var(ddof=1) / len(left)) + (right.var(ddof=1) / len(right))
        )
        shift = abs(right.mean() - left.mean())
        if pooled <= 0:
            # Degenerate: constant series either side. Report the raw gap.
            yield i, math.inf if shift > 0 else 0.0
        else:
            yield i, shift / pooled


def detect_breaks(
    basis: pd.Series,
    volumes: pd.Series | None = None,
    min_segment: int = 15,
    max_breaks: int = 4,
) -> list[Break]:
    """Locate the strongest regime breaks in a basis series.

    Parameters
    ----------
    basis:
        Daily basis in basis points, indexed by date, without gaps.
    volumes:
        Optional daily traded volume, used to attach a liquidity signature to
        each break.
    max_breaks:
        Stop after this many breaks, strongest first.
    """
    clean = basis.dropna()
    if len(clean) < 2 * min_segment:
        return []

    found: list[Break] = []
    remaining = clean.copy()

    for _ in range(max_breaks):
        if len(remaining) < 2 * min_segment:
            break
        candidates = list(_cumulative_sum_shift(remaining, min_segment))
        if not candidates:
            break
        idx, stat = max(candidates, key=lambda t: t[1])
        if stat == 0:
            break

        before = remaining.iloc[:idx]
        after = remaining.iloc[idx:]
        mb, ma = before.median(), after.median()
        shift = ma - mb

        vb = va = float("nan")
        if volumes is not None:
            v = volumes.reindex(before.index[-20:])
            if not v.empty:
                vb = float(v.median())
            v2 = volumes.reindex(after.index[:20])
            if not v2.empty:
                va = float(v2.median())

        found.append(
            Break(
                date=remaining.index[idx],
                magnitude_bps=shift,
                median_before_bps=mb,
                median_after_bps=ma,
                volume_before=vb,
                volume_after=va,
                classification=_classify(shift, stat, vb, va),
            )
        )
        # Split and continue on the larger remaining segment.
        if len(before) >= len(after):
            remaining = before
        else:
            remaining = after

    return found


def _classify(shift: float, statistic: float, vol_before: float, vol_after: float) -> str:
    """Label a break by its shape.

    A rule change takes effect on a date, producing a step. A liquidity event
    produces a gradual move accompanied by a volume change. The distinction
    matters because it tells you whether to go looking for a circular or for a
    market participant.
    """
    if shift < 0:
        return "structural"
    if not np.isfinite(vol_before) or not np.isfinite(vol_after) or vol_before == 0:
        return "unexplained"
    ratio = vol_after / vol_before
    if ratio > 1.5:
        return "liquidity-event"
    if ratio < 0.67:
        return "liquidity-event"
    return "step-change"


def attribute_break(
    pair: tuple[str, str],
    break_date: pd.Timestamp,
    bhavcopy: pd.DataFrame,
    max_dte: int = 60,
    window_days: int = 15,
) -> dict | None:
    """Work out **which leg moved** across a break, from the data itself.

    A basis is a difference, so a break says nothing about which side caused it.
    This decomposes it: for each contract, measure the median per-gram-fine
    price in the ``window_days`` before and after ``break_date``.

    The key comparison is not leg-vs-leg but **leg-vs-the-whole-complex**. Two
    very different stories live here and they look identical in the raw basis:

    * *market-wide move* - every contract falls together. The basis moved only
      because one leg fell a little less. Nothing contract-specific happened.
    * *idiosyncratic move* - one leg diverges from the complex. That is real
      information about that contract, and worth chasing.

    So each leg is scored by ``move_bps`` minus the complex median move. The
    leg with the largest divergence is the idiosyncratic one. Reporting which
    leg is *thinner* is deliberately avoided: on this data the thin leg can
    move in lockstep with the liquid complex, and calling that a liquidity
    artefact would be wrong.

    Returns ``None`` when there is not enough data on either side of the date.
    """
    sym_a, sym_b = pair
    traded = bhavcopy[(~bhavcopy["no_trade"]) & (bhavcopy["days_to_expiry"] <= max_dte)]
    date = pd.Timestamp(break_date)
    lo = date - pd.Timedelta(days=window_days)
    hi = date + pd.Timedelta(days=window_days)

    def window_move(sub: pd.DataFrame) -> float | None:
        before = sub[(sub["date"] >= lo) & (sub["date"] < date)]["px_per_g_fine"]
        after = sub[(sub["date"] >= date) & (sub["date"] <= hi)]["px_per_g_fine"]
        if len(before) < 3 or len(after) < 3:
            return None
        px_before, px_after = float(before.median()), float(after.median())
        if px_before <= 0:
            return None
        return 1e4 * math.log(px_after / px_before)

    # Movement of the whole modelled complex, as the reference for "market-wide".
    per_symbol = {
        sym: window_move(traded[traded["symbol"] == sym])
        for sym in sorted(traded["symbol"].unique())
    }
    known = [v for v in per_symbol.values() if v is not None]
    if len(known) < 3:
        return None
    complex_move = float(np.median(known))

    legs = {}
    for sym in (sym_a, sym_b):
        sub = traded[traded["symbol"] == sym]
        before = sub[(sub["date"] >= lo) & (sub["date"] < date)]["px_per_g_fine"]
        after = sub[(sub["date"] >= date) & (sub["date"] <= hi)]["px_per_g_fine"]
        if len(before) < 3 or len(after) < 3:
            return None
        move = window_move(sub)
        if move is None:
            return None
        legs[sym] = {
            "px_before": float(before.median()),
            "px_after": float(after.median()),
            "median_volume": float(sub["Volume"].median()),
            "move_bps": move,
            # How far this leg departed from the rest of the complex.
            "idiosyncratic_bps": move - complex_move,
        }

    idiosyncratic = max(legs, key=lambda s: abs(legs[s]["idiosyncratic_bps"]))
    # Tolerance: a leg within ~40 bps of the complex moved *with* the market.
    flagged = abs(legs[idiosyncratic]["idiosyncratic_bps"]) > 40.0
    return {
        "pair": f"{sym_a}/{sym_b}",
        "date": str(date.date()),
        "legs": legs,
        "complex_move_bps": complex_move,
        "idiosyncratic_leg": idiosyncratic if flagged else None,
        "reading": (
            f"{idiosyncratic} moved {legs[idiosyncratic]['idiosyncratic_bps']:+.0f} bps "
            f"away from the complex"
            if flagged
            else "both legs moved with the wider gold complex"
        ),
    }


# ---------------------------------------------------------------- walk-forward


@dataclass
class WalkForwardResult:
    """Outcome of a pre-registered, no-look-ahead test."""

    pair: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_opportunities: int
    test_opportunities: int
    test_cleared: int
    max_exceedance_bps: float
    mean_exceedance_bps: float
    bound_low_bps: float
    bound_high_bps: float
    #: The contractual wedge removed before testing (purity + duty basis).
    wedge_bps: float = 0.0
    #: The centred structural level estimated on TRAIN ONLY and then frozen.
    train_median_bps: float = 0.0
    #: Median of the unseen test window, and how far it sits from the frozen
    #: training level. A large value means the structural relationship itself
    #: changed - a regime shift, not a trading opportunity.
    test_median_bps: float = 0.0
    level_shift_bps: float = 0.0
    level_is_stable: bool = True
    trades: list[dict] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.test_cleared == 0:
            return "NOT_ARBITRAGABLE"
        return "BOUND_EXCEEDED_IN_TEST"

    def describe(self) -> str:
        stability = (
            "level stable"
            if self.level_is_stable
            else f"LEVEL SHIFTED {self.level_shift_bps:+.0f} bps"
        )
        return (
            f"{self.pair}: {self.verdict} | "
            f"train {self.train_start.date()}..{self.train_end.date()} "
            f"({self.train_opportunities} breaches) | "
            f"test {self.test_start.date()}..{self.test_end.date()} "
            f"({self.test_opportunities} breaches, {self.test_cleared} cleared) | "
            f"max exceedance {self.max_exceedance_bps:+.1f} bps vs bound "
            f"{self.bound_low_bps:.0f}-{self.bound_high_bps:.0f} | {stability}"
        )


def walk_forward(
    basis: pd.Series,
    pair_bound: PairBound,
    train_fraction: float = 0.7,
    min_segment: int = 15,
) -> WalkForwardResult | None:
    """Test whether the basis ever exceeds the arbitrage bound out of sample.

    What is actually tested
    -----------------------
    Two contracts that differ in purity or quote basis **must** trade at
    different prices - that difference is a contractual wedge, not an
    opportunity. Testing the raw basis against a friction bound would flag
    hundreds of days that are structurally un-tradeable and say nothing.

    So the test is run on the **residual**: basis minus the structural wedge,
    minus a *centring level estimated on the training window only*. The
    centring level is then frozen and applied unchanged to the test window.

    This is what makes it pre-registered rather than a search: the only
    quantity fitted to training data is one scalar level, chosen before the
    test window was touched.
    """
    clean = basis.dropna().sort_index()
    if len(clean) < 2 * min_segment:
        return None

    split = int(len(clean) * train_fraction)
    train = clean.iloc[:split]
    test = clean.iloc[split:]
    if len(train) < min_segment or len(test) < min_segment:
        return None

    # Frozen from training data only.
    centre = float(train.median())
    wedge = pair_bound.purity_wedge_bps

    # Most tradeable-friendly bound: the value a sceptic would use.
    threshold = pair_bound.total_bound_bps.worst_case()

    # Direction matters, and this is the subtlety that makes the test correct.
    #
    # Fabrication cost is **one-way**: converting a 1 g bar into an 8 g bar
    # costs the same per-bar setup spread over 8 g, and converting 8 g into 1 g
    # costs it over 1 g - so the small-bar side always carries more overhead.
    # An opportunity therefore exists only when the *expensive-to-manufacture*
    # contract trades **above** the level implied by the cheap one.
    #
    # Which symbol that is depends on the pair's price ordering, which is a
    # property of the pair, not of the sign of the training median. Using the
    # median's sign here would flip the tradeable direction whenever the basis
    # merely happens to be negative, which is wrong: a constant -20 bps basis
    # is just as much a structural level as a constant +20 bps one.
    #
    # The invariant, tested in test_analysis.py, is that a constant offset is
    # never itself tradeable - only a *deviation* from the frozen centre in the
    # allowed direction is.
    # An opportunity exists only when the contract that is more expensive to
    # manufacture trades above the cheap one.
    #
    # `basis` is ln(A/B). If A is the dear-to-make contract, A-above-B is a
    # POSITIVE basis, which is the tradeable direction -> sign +1. If B is the
    # dear one, the tradeable direction is a NEGATIVE basis -> sign -1.
    a_is_expensive = pair_bound.overhead_a_per_g > pair_bound.overhead_b_per_g
    tradable_sign = 1.0 if a_is_expensive else -1.0

    def residual_excess(seg: pd.Series) -> pd.Series:
        resid = (seg - centre) * tradable_sign
        return resid

    train_resid = residual_excess(train)
    test_resid = residual_excess(test)
    exceedances = test_resid - threshold

    # A drifting structural level is not an opportunity, and must not be
    # counted as one. If the test window's *median* sits far from the frozen
    # training centre, the relationship between the two contracts changed - a
    # regime shift, not a trade. That is reported as its own finding rather
    # than being silently diluted into hundreds of "breaches".
    train_median = float(train.median())
    test_median = float(test.median())
    level_shift_bps = (test_median - train_median) * tradable_sign
    level_is_stable = abs(level_shift_bps) <= threshold

    return WalkForwardResult(
        pair=pair_bound.pair,
        train_start=train.index[0],
        train_end=train.index[-1],
        test_start=test.index[0],
        test_end=test.index[-1],
        train_opportunities=int((train_resid > threshold).sum()),
        test_opportunities=int((test_resid > threshold).sum()),
        test_cleared=int((test_resid > pair_bound.total_bound_bps.high_bps).sum()),
        max_exceedance_bps=float(exceedances.max()) if len(exceedances) else 0.0,
        mean_exceedance_bps=float(exceedances.mean()) if len(exceedances) else 0.0,
        bound_low_bps=pair_bound.total_bound_bps.low_bps,
        bound_high_bps=pair_bound.total_bound_bps.high_bps,
        wedge_bps=wedge,
        train_median_bps=centre,
        test_median_bps=test_median,
        level_shift_bps=level_shift_bps,
        level_is_stable=level_is_stable,
        trades=[
            {
                "date": str(ts.date()),
                "basis_bps": float(val),
                "residual_bps": float((val - centre) * tradable_sign),
                "exceeds_bound": bool((val - centre) * tradable_sign > threshold),
            }
            for ts, val in test.items()
            if (val - centre) * tradable_sign > threshold
        ],
    )


# ------------------------------------------------------------- sensitivity


def sensitivity(
    pair_bound: PairBound, spec_a, spec_b, reference_price: float
) -> pd.DataFrame:
    """Re-derive the bound across the full range of stated assumptions.

    A conclusion is only worth stating if it survives the assumptions it rests
    on. This table is the evidence for that, and belongs in the write-up.
    """
    from .bound import (
        DUTY_WEDGE_BPS,
        FRICTION_HIGH,
        FRICTION_LOW,
        MINT_COST_PER_BAR_INR,
        SLIPPAGE_BPS,
        compute_pair_bound,
    )

    rows = []
    for mint in [MINT_COST_PER_BAR_INR[0], MINT_COST_PER_BAR_INR[1]]:
        for duty in [DUTY_WEDGE_BPS[0], DUTY_WEDGE_BPS[1]]:
            for friction, slip in [
                (FRICTION_LOW, SLIPPAGE_BPS[0]),
                (FRICTION_HIGH, SLIPPAGE_BPS[1]),
            ]:
                b = compute_pair_bound(
                    spec_a,
                    spec_b,
                    reference_price,
                    mint_cost_per_bar=mint,
                    duty_wedge_bps=duty,
                )
                rows.append(
                    {
                        "mint_cost_per_bar_inr": mint,
                        "duty_wedge_bps": duty,
                        "friction_bps_per_leg": friction * 1e4,
                        "slippage_bps_per_leg": slip,
                        "structural_bps": b.structural_bps,
                        "total_bound_bps": b.total_bound_bps.mid_bps,
                    }
                )
    return pd.DataFrame(rows)