"""Build an HTML report plus a basis-history series for the charts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cli import _load, build_report
from .ingest import matched_basis


def history(report_input: Path, max_points: int = 400) -> dict[str, list[dict]]:
    """Basis series per pair, downsampled for the sparkline."""
    frame = _load(report_input)
    basis = matched_basis(frame)
    out: dict[str, list[dict]] = {}
    for col in basis.columns:
        series = basis[col].dropna()
        if len(series) < 2:
            continue
        step = max(1, len(series) // max_points)
        sampled = series.iloc[::step]
        out[col] = [
            {"x": i, "y": float(v), "label": str(ts.date())}
            for i, (ts, v) in enumerate(sampled.items())
        ]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="arbbound.build")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    frame = _load(args.input)
    report = build_report(frame)
    (args.outdir / "report.json").write_text(json.dumps(report, indent=2))

    from .report import render

    html = render(report, history(args.input))
    (args.outdir / "index.html").write_text(html)

    print(f"wrote {args.outdir}/report.json and {args.outdir}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())