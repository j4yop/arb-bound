"""Structural arbitrage bound for MCX cross-contract gold spreads.

The central economic claim of this project
------------------------------------------
MCX lists the same metal in four physical delivery sizes. Converting metal
between two of those sizes requires re-minting: you hand in a 100 g bar and
want back, say, eight 8 g bars.

Refining and minting cost is dominated by a **per-bar** fixed cost (setup,
assay, serialisation, logistics), not a per-gram cost. So the fabrication
overhead per gram scales roughly as ``1 / bar_size``:

    overhead_per_gram = fixed_cost_per_bar / bar_grams

A 1 g bar therefore carries roughly 8x the per-gram fabrication overhead of an
8 g bar. That difference is a **structural constant**, not a dislocation.

Consequence
-----------
The observed GOLDPETAL premium is the cost of physically closing the trade.
It can only be captured by a participant who already holds bar inventory and
can accept assay, wastage and warehouse risk. A participant trading only
futures cannot short into compulsory delivery.

This module turns that argument into a falsifiable bound: for each contract
pair, how large must the gross gap be before any participant could profit, and
how often does the observed gap clear it?

The bound is deliberately built from *sourced* parameters with sensitivity
ranges, not tuned to make a conclusion appear.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ContractSpec


# ------------------------------------------------------------------ constants

#: Indicative per-bar minting/refining charge in INR. This is a **stated
#: assumption**, not a measured exchange constant: MCX does not publish it.
#: The bound is therefore reported across a range, and the conclusion is only
#: claimed where it survives the whole range.
MINT_COST_PER_BAR_INR = (20.0, 60.0)  # (low, high)

#: Cash-market friction on the two legs, as a fraction of notional.
#: Brokerage INR 20 per order (Zerodha flat) + GST 18% on brokerage,
#: STT/CTT, stamp duty, exchange and SEBI turnover fees.
FRICTION_LOW = 0.0004   # 4 bps  - tight: big contract, liquid
FRICTION_HIGH = 0.0035  # 35 bps - realistic: retail size, thin contract

#: Conservative slippage in bps of notional per leg, reflecting that the
#: bhavcopy records settlement prices, not executable fills.
SLIPPAGE_BPS = (2.0, 10.0)

#: Purity/quote-basis structural wedge.
#:
#: GOLDM is a 995-purity contract quoting duty-inclusive Ex-Ahmedabad, while
#: GOLDTEN / GOLDGUINEA / GOLDPETAL are 999-purity retail bars quoting their own
#: basis. These are **contractually different things**, so a persistent price
#: difference between them is a *structural constant of the contract design*,
#: not an arbitrage opportunity.
#:
#: The purity part is exactly 999/995. The duty part is not a number we may
#: assume: import duty on bullion is set by the Government of India and has
#: changed several times, so it is carried as an explicit, **stated**
#: parameter with a range and is reported as a sensitivity, never as a fitted
#: constant. What matters for the conclusion is that it is a *wedge* - a
#: standing, non-tradeable difference - not a mispricing.
PURITY_WEDGE = 0.999 / 0.995 - 1.0  # ~40.2 bps of fine-gold content

#: Indicative import-duty-inclusive wedge between the 995 duty-inclusive quote
#: and the 999 retail-bar quote, in bps of notional. Carried as a range because
#: the exact duty is policy-set and has moved repeatedly.
DUTY_WEDGE_BPS = (0.0, 400.0)


# --------------------------------------------------------------- bound types


@dataclass(frozen=True)
class CostRange:
    """A cost expressed as a low/high band in basis points of notional."""

    low_bps: float
    high_bps: float

    @property
    def mid_bps(self) -> float:
        return 0.5 * (self.low_bps + self.high_bps)

    def worst_case(self) -> float:
        """The bound a sceptic should use: the most generous to trading."""
        return self.low_bps


@dataclass(frozen=True)
class PairBound:
    """The minimum gross gap required before a cross-contract spread is
    tradeable, for one pair of contracts."""

    pair: str
    symbol_a: str
    symbol_b: str

    #: Per-gram fabrication overhead of each contract, in INR.
    overhead_a_per_g: float
    overhead_b_per_g: float

    #: Contractual wedge from differing purity / quote basis, in bps.
    #: This is a standing structural difference, not a tradeable gap.
    purity_wedge_bps: float

    #: The physical component: the fabrication gap that must be covered.
    structural_bps: float

    #: Full bound including statutory friction and slippage on both legs.
    friction_bps: CostRange
    total_bound_bps: CostRange

    #: Whether the two contracts differ in purity, which makes a portion of
    #: their price difference contractual rather than tradeable.
    purity_mismatch: bool

    def clears(self, observed_bps: float) -> bool:
        """Did the observed gap exceed the most tradeable-friendly bound?"""
        return observed_bps > self.total_bound_bps.worst_case()

    def describe(self) -> str:
        return (
            f"{self.symbol_a}/{self.symbol_b}: "
            f"structural {self.structural_bps:.0f} bps, "
            f"total bound {self.total_bound_bps.low_bps:.0f}-"
            f"{self.total_bound_bps.high_bps:.0f} bps"
        )


# ------------------------------------------------------------------ machinery


def fabrication_overhead_per_gram(spec: ContractSpec, mint_cost_per_bar: float) -> float:
    """INR per gram of fabrication overhead for one contract.

    ``mint_cost_per_bar / lot_grams`` - the per-bar cost spread over the
    physical size of the bar you actually receive.
    """
    return mint_cost_per_bar / spec.lot_grams


def structural_gap_per_gram(
    spec_a: ContractSpec, spec_b: ContractSpec, mint_cost_per_bar: float
) -> float:
    """INR per gram that must be paid just to physically convert A into B.

    This is the structural component of the bound. It is a *physical*
    requirement, not a market friction: you cannot net it away with a better
    broker or a faster fill.
    """
    return abs(
        fabrication_overhead_per_gram(spec_a, mint_cost_per_bar)
        - fabrication_overhead_per_gram(spec_b, mint_cost_per_bar)
    )


def bps_per_gram(price_per_gram: float) -> float:
    """Basis points corresponding to one rupee, at the given price level."""
    if price_per_gram <= 0:
        raise ValueError("price_per_gram must be positive")
    return 1e4 / price_per_gram


def compute_pair_bound(
    spec_a: ContractSpec,
    spec_b: ContractSpec,
    reference_price_per_gram: float,
    mint_cost_per_bar: float | None = None,
    duty_wedge_bps: float | None = None,
) -> PairBound:
    """Build the arbitrage bound for one contract pair.

    Parameters
    ----------
    reference_price_per_gram:
        Typical per-gram fine-gold price, used to convert rupee amounts into
        basis points. Using the actual market level (not a constant) keeps the
        conversion honest across the sample.
    mint_cost_per_bar:
        Override the per-bar minting assumption (mainly for tests and for
        sensitivity analysis). Defaults to the midpoint of the sourced range.
    duty_wedge_bps:
        Override the duty/quote-basis wedge. Defaults to the midpoint of the
        stated range. Because this is the *least certain* input, callers that
        need a conclusion should sweep it via ``sensitivity``.
    """
    if mint_cost_per_bar is None:
        mint_cost_per_bar = 0.5 * (MINT_COST_PER_BAR_INR[0] + MINT_COST_PER_BAR_INR[1])
    if duty_wedge_bps is None:
        duty_wedge_bps = 0.5 * (DUTY_WEDGE_BPS[0] + DUTY_WEDGE_BPS[1])

    overhead_a = fabrication_overhead_per_gram(spec_a, mint_cost_per_bar)
    overhead_b = fabrication_overhead_per_gram(spec_b, mint_cost_per_bar)
    gap_inr = abs(overhead_a - overhead_b)
    fabrication_bps = gap_inr * bps_per_gram(reference_price_per_gram)

    # Purity is only a wedge when the two contracts actually differ in fineness.
    purity_mismatch = abs(spec_a.purity - spec_b.purity) > 1e-9
    if purity_mismatch:
        fineness_bps = abs(PURITY_WEDGE) * 1e4
    else:
        fineness_bps = 0.0

    # Duty/quote basis differs whenever the contracts quote on different bases.
    quote_mismatch = spec_a.quote_basis != spec_b.quote_basis
    wedge_bps = fineness_bps + (duty_wedge_bps if quote_mismatch else 0.0)

    structural = fabrication_bps + wedge_bps

    # Friction applies to both legs, plus two-sided slippage.
    friction_low = 2 * (FRICTION_LOW * 1e4) + 2 * SLIPPAGE_BPS[0]
    friction_high = 2 * (FRICTION_HIGH * 1e4) + 2 * SLIPPAGE_BPS[1]

    return PairBound(
        pair=f"{spec_a.symbol}/{spec_b.symbol}",
        symbol_a=spec_a.symbol,
        symbol_b=spec_b.symbol,
        overhead_a_per_g=overhead_a,
        overhead_b_per_g=overhead_b,
        purity_wedge_bps=wedge_bps,
        structural_bps=structural,
        friction_bps=CostRange(friction_low, friction_high),
        total_bound_bps=CostRange(
            structural + friction_low, structural + friction_high
        ),
        purity_mismatch=purity_mismatch,
    )