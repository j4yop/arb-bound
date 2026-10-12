"""Build an HTML report plus a basis-history series for the charts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cli import _load, build_report
from .ingest import basis_history as history
from .playground import build_playground


def _sample_for_embedding(path: Path) -> str:
    """The full input CSV, to be gzipped into the playground page.

    The whole fixture gzips to a few hundred KB, so the default in-browser demo
    runs the identical analysis the command line does - across all four
    contracts and the entire sample window. Truncating by row count is avoided
    deliberately: it silently drops whichever contracts happen to sort last.
    """
    return path.read_text()


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

    html = render(report, history(frame))
    (args.outdir / "index.html").write_text(html)

    # The playground ships this package's own source so the browser can run the
    # genuine pipeline. See arbbound/playground.py.
    build_playground(
        Path(__file__).parent,
        _sample_for_embedding(args.input),
        args.outdir / "playground.html",
        sample_label=f"bundled sample ({args.input.name})",
    )

    print(f"wrote {args.outdir}/report.json, index.html and playground.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())