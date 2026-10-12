"""Command line interface: bhavcopy in, arbitrage verdict out.

Usage
-----
    python -m arbbound.cli --input data/fixture_gold_2023-2026.csv
    python -m arbbound.cli --input data/bhavcopy_2026-09-10.json --json out.json
    python -m arbbound.cli --sensitivity

The tool is deterministic and offline. Given the same input it always produces
the same verdict, which is what makes it checkable rather than decorative.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .analysis import (
    attribute_break,
    check_executability,
    detect_breaks,
    sensitivity,
    walk_forward,
)
from .bound import compute_pair_bound
from .contracts import CONTRACTS, pairs, spec_for
from .ingest import (
    load_csv_bhavcopy,
    load_json_bhavcopy,
    matched_basis,
    reference_price,
)


def _load(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        return load_json_bhavcopy(path)
    return load_csv_bhavcopy(path)


def sensitivity_report(frame: pd.DataFrame) -> dict:
    """Sweep every stated assumption across its range, for every pair.

    Read off the *same* input as the verdict, so the reference price is the
    market's, not a constant typed into the source. The point of the sweep is
    that a conclusion is only worth stating if it survives the whole range of
    assumptions it rests on.
    """
    ref = reference_price(frame)
    out = {}
    for a, b in pairs():
        table = sensitivity(
            compute_pair_bound(spec_for(a), spec_for(b), ref),
            spec_for(a),
            spec_for(b),
            ref,
        )
        structural = table["structural_bps"]
        total = table["total_bound_bps"]
        out[f"{a}/{b}"] = {
            "reference_price_inr_per_gram_fine": ref,
            "min_structural_bps": float(structural.min()),
            "max_structural_bps": float(structural.max()),
            "min_total_bound_bps": float(total.min()),
            "max_total_bound_bps": float(total.max()),
            "corners": table.to_dict(orient="records"),
        }
    return out


def build_report(frame: pd.DataFrame) -> dict:
    """Produce the full verdict structure from a loaded bhavcopy frame."""
    traded = frame[~frame["no_trade"]]
    basis = matched_basis(frame)

    ref_px = reference_price(frame)
    bounds = {}
    walkforwards = {}
    breaks = {}
    executability = {}

    # Volume context for each pair, taken from the thin contract in the pair -
    # that is where the interesting behaviour happens.
    vol_by_symbol = {
        sym: traded[traded["symbol"] == sym].groupby("date")["Volume"].sum()
        for sym in CONTRACTS
    }

    for a, b in pairs():
        pair_name = f"{a}/{b}"
        pb = compute_pair_bound(spec_for(a), spec_for(b), ref_px)
        bounds[pair_name] = {
            "pair": pair_name,
            "purity_mismatch": pb.purity_mismatch,
            "structural_bps": pb.structural_bps,
            "purity_wedge_bps": pb.purity_wedge_bps,
            "bound_low_bps": pb.total_bound_bps.low_bps,
            "bound_high_bps": pb.total_bound_bps.high_bps,
            "overhead_a_inr_per_g": pb.overhead_a_per_g,
            "overhead_b_inr_per_g": pb.overhead_b_per_g,
        }

        if pair_name in basis.columns:
            wf = walk_forward(basis[pair_name], pb)
            if wf is not None:
                walkforwards[pair_name] = {
                    "verdict": wf.verdict,
                    "train_window": [str(wf.train_start.date()), str(wf.train_end.date())],
                    "test_window": [str(wf.test_start.date()), str(wf.test_end.date())],
                    "train_median_bps": wf.train_median_bps,
                    "test_median_bps": wf.test_median_bps,
                    "level_shift_bps": wf.level_shift_bps,
                    "level_is_stable": wf.level_is_stable,
                    "wedge_bps": wf.wedge_bps,
                    "train_breaches": wf.train_opportunities,
                    "test_breaches": wf.test_opportunities,
                    "test_cleared_strict_bound": wf.test_cleared,
                    "max_exceedance_bps": wf.max_exceedance_bps,
                    "mean_exceedance_bps": wf.mean_exceedance_bps,
                    "bound_low_bps": wf.bound_low_bps,
                    "bound_high_bps": wf.bound_high_bps,
                }

                # Every day the test flagged gets re-examined against what the
                # exchange actually printed, to separate a real gap from an
                # unreachable settlement quote.
                if wf.test_cleared > 0:
                    flagged = [pd.Timestamp(t["date"]) for t in wf.trades]
                    checks = check_executability(
                        flagged, (a, b), frame, basis[pair_name]
                    )
                    executability[pair_name] = [
                        {
                            "date": str(c.date.date()),
                            "basis_bps": c.basis_bps,
                            "printed_band_bps": [c.band_low_bps, c.band_high_bps],
                            "hi_lo_cover": c.hi_lo_cover,
                            "volume_sufficient": c.volume_sufficient,
                            "executable": c.executable,
                        }
                        for c in checks
                    ]

            pair_vol = vol_by_symbol.get(b)
            pair_breaks = detect_breaks(basis[pair_name], pair_vol)
            breaks[pair_name] = [
                {
                    "date": str(br.date.date()),
                    "magnitude_bps": br.magnitude_bps,
                    "median_before_bps": br.median_before_bps,
                    "median_after_bps": br.median_after_bps,
                    "volume_before": br.volume_before,
                    "volume_after": br.volume_after,
                    "volume_ratio": (
                        br.volume_after / br.volume_before
                        if br.volume_before and br.volume_before == br.volume_before
                        else None
                    ),
                    "classification": br.classification,
                    # Which leg actually moved, and whether it was the thin one.
                    "attribution": attribute_break((a, b), br.date, frame),
                }
                for br in pair_breaks
            ]

    return {
        "reference_price_inr_per_gram_fine": ref_px,
        "sample": {
            "rows": int(len(frame)),
            "traded_rows": int(len(traded)),
            "start": str(frame["date"].min().date()),
            "end": str(frame["date"].max().date()),
            "contracts": sorted(frame["symbol"].unique().tolist()),
        },
        "bounds": bounds,
        "sensitivity": sensitivity_report(frame),
        "walk_forward": walkforwards,
        "regime_breaks": breaks,
        "executability": executability,
        "verdict_summary": {
            "pairs_tested": len(walkforwards),
            "pairs_ever_clearing_bound": sum(
                1 for w in walkforwards.values() if w["test_cleared_strict_bound"] > 0
            ),
            "flagged_days_total": sum(len(v) for v in executability.values()),
            "flagged_days_executable": sum(
                sum(1 for c in v if c["executable"]) for v in executability.values()
            ),
        },
    }


def _print_human(report: dict) -> None:
    s = report["sample"]
    print("=" * 74)
    print("  ARB-BOUND  |  MCX cross-contract gold arbitrage feasibility")
    print("=" * 74)
    print(f"Sample      : {s['start']} -> {s['end']}  ({s['traded_rows']:,} traded rows)")
    print(f"Contracts   : {', '.join(s['contracts'])}")
    print(f"Reference   : INR {report['reference_price_inr_per_gram_fine']:,.2f} per gram of fine gold")
    print()

    print("STRUCTURAL BOUND  (gross gap required before a trade can profit)")
    print("-" * 74)
    print(f"{'pair':<26} {'wedge':>8} {'structural':>11} {'bound band':>16}")
    for name, b in sorted(report["bounds"].items()):
        print(
            f"{name:<26} {b['purity_wedge_bps']:>7.0f}b {b['structural_bps']:>10.0f}b "
            f"{b['bound_low_bps']:>7.0f}-{b['bound_high_bps']:<7.0f}b"
        )
    print("  wedge = contractual purity + duty-basis difference (not tradeable)")
    print()

    print("WALK-FORWARD TEST  (residual basis, level frozen from train only)")
    print("-" * 74)
    for name, w in sorted(report["walk_forward"].items()):
        flag = "" if w["level_is_stable"] else f"  ** LEVEL SHIFTED {w['level_shift_bps']:+.0f} bps **"
        print(f"{name:<26} {w['verdict']:<20} breaches test={w['test_breaches']:<4} "
              f"cleared={w['test_cleared_strict_bound']}{flag}")
        if not w["level_is_stable"]:
            print(f"{'':26} frozen train level {w['train_median_bps']:+.1f} bps, "
                  f"test median {w['test_median_bps']:+.1f} bps")
        else:
            print(f"{'':26} max residual exceedance {w['max_exceedance_bps']:+.1f} bps vs bound "
                  f"{w['bound_low_bps']:.0f}-{w['bound_high_bps']:.0f} bps")
    print()

    print("DETECTED REGIME BREAKS  (structural cost cannot jump - these are events)")
    print("-" * 74)
    any_break = False
    for name, bs in sorted(report["regime_breaks"].items()):
        for br in bs:
            if abs(br["magnitude_bps"]) < 25:
                continue
            any_break = True
            vr = br["volume_ratio"]
            vol = f"vol x{vr:.1f}" if vr else "vol n/a"
            print(f"{name:<26} {br['date']}  {br['median_before_bps']:+8.1f} -> "
                  f"{br['median_after_bps']:+7.1f} bps   {br['classification']:<16} {vol}")
            attr = br.get("attribution")
            if attr and attr.get("reading"):
                print(f"{'':26} attribution: {attr['reading']} "
                      f"(complex {attr['complex_move_bps']:+.0f} bps)")
    if not any_break:
        print("(no break above 25 bps detected)")
    print()

    vs = report["verdict_summary"]
    print("EXECUTABILITY OF FLAGGED DAYS  (settlement prints are not executable quotes)")
    print("-" * 74)
    if not report["executability"]:
        print("(no days cleared the bound, so nothing to test)")
    else:
        for name, checks in sorted(report["executability"].items()):
            ex = sum(1 for c in checks if c["executable"])
            print(f"{name:<26} {len(checks):>3} flagged   {ex:>3} executable   "
                  f"{ex}/{len(checks)} would have been reachable")
    print()

    print("=" * 74)
    if vs["pairs_ever_clearing_bound"] == 0:
        print("  VERDICT: No cross-contract spread cleared its arbitrage bound in the")
        print("  unseen test window. The observed gaps are consistent with the")
        print("  structural cost of physically re-minting between bar sizes.")
    else:
        reachable = vs["flagged_days_executable"]
        print(f"  VERDICT: {vs['pairs_ever_clearing_bound']} pair(s) printed gaps above the bound.")
        print(f"  Of {vs['flagged_days_total']} flagged days, {reachable} were reachable")
        print("  within the exchange's own printed high/low bands and liquidity.")
        print("  Settlement prints alone do not establish a tradeable edge.")
    print("=" * 74)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="arbbound", description=__doc__)
    ap.add_argument("--input", type=Path, help="bhavcopy .json or .csv")
    ap.add_argument("--json", type=Path, help="write the full report as JSON")
    ap.add_argument("--sensitivity", action="store_true",
                    help="sweep every stated assumption across its range (needs --input)")
    args = ap.parse_args(argv)

    if args.sensitivity:
        frame = _load(args.input) if args.input else None
        if frame is None:
            ap.error("--sensitivity requires --input so the reference price is real")
        report = sensitivity_report(frame)
        ref = report[next(iter(report))]["reference_price_inr_per_gram_fine"]
        print(f"Reference price: INR {ref:,.2f} per gram fine (from the supplied input)\n")
        for name, s in report.items():
            print(f"{name}")
            print(f"  structural {s['min_structural_bps']:.0f}-{s['max_structural_bps']:.0f} bps"
                  f"   total bound {s['min_total_bound_bps']:.0f}-{s['max_total_bound_bps']:.0f} bps"
                  f"   across {len(s['corners'])} assumption corners")
            for c in s["corners"]:
                print(f"    mint {c['mint_cost_per_bar_inr']:>4.0f}/bar  "
                      f"duty {c['duty_wedge_bps']:>4.0f}b  "
                      f"fric {c['friction_bps_per_leg']:>4.0f}b  "
                      f"slip {c['slippage_bps_per_leg']:>4.0f}b  -> "
                      f"bound {c['total_bound_bps']:>6.0f}b")
        return 0

    if not args.input:
        ap.error("--input is required")
    if not args.input.exists():
        print(f"error: no such file: {args.input}", file=sys.stderr)
        return 2

    frame = _load(args.input)
    report = build_report(frame)
    _print_human(report)

    if args.json:
        args.json.write_text(json.dumps(report, indent=2))
        print(f"\nJSON report written to {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())