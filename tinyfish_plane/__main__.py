"""TinyFish CLI for arb-bound.

    python -m tinyfish_plane wallet                      # balance + rates
    python -m tinyfish_plane live                        # today's bhavcopy, parsed
    python -m tinyfish_plane circulars 01/10/2024 31/12/2024
                                                          # dated archive search
    python -m tinyfish_plane search "gold petal contract" # free web search

Everything is printed as JSON so it can be piped, diffed and archived. The key
is read from the environment and is never printed.
"""

from __future__ import annotations

import argparse
import json
import sys

from .plane import (
    TinyFishUnavailable,
    archive_circulars,
    live_gold_frame,
    search,
    wallet,
)


def _print(payload) -> None:
    sys.stdout.write(json.dumps(payload, indent=1, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tinyfish_plane", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("wallet", help="show wallet balance and per-unit rates")
    sub.add_parser("live", help="fetch and parse today's live MCX bhavcopy")
    sp = sub.add_parser("circulars", help="date-filter MCX's circular archive")
    sp.add_argument("date_from", help="e.g. 01/10/2024")
    sp.add_argument("date_to", help="e.g. 31/12/2024")
    sp.add_argument("--max-wait", type=float, default=1800.0)
    s2 = sub.add_parser("search", help="free TinyFish web search")
    s2.add_argument("query")

    args = ap.parse_args(argv)

    try:
        if args.cmd == "wallet":
            w = wallet()
            _print(
                {
                    "available_balance": w.get("available_balance"),
                    "currency": w.get("currency"),
                    "rates": {
                        m["label"]: f"{m['unit_amount']} / {m['per']}"
                        for m in w.get("rates", {}).get("meters", [])
                    },
                }
            )
        elif args.cmd == "live":
            frame, source = live_gold_frame()
            # Same predicate the analysis layer uses, so the live path is
            # filtered by the project's own definition of "thin", not a new one.
            traded = frame[~frame["no_trade"]]
            golds = sorted(
                {s.strip() for s in frame["symbol"].astype(str) if "GOLD" in s.upper()}
            )
            _print(
                {
                    "source": source,
                    "rows": int(len(frame)),
                    "rows_with_trades": int(len(traded)),
                    "date_range": [
                        str(frame["date"].min().date()),
                        str(frame["date"].max().date()),
                    ],
                    "gold_symbols": [g for g in golds if g],
                    "gold_rows": {
                        g: int((frame["symbol"].str.strip() == g).sum())
                        for g in golds
                        if g
                    },
                }
            )
            sys.stderr.write(
                f"parsed {len(frame)} rows ({len(traded)} with trades); "
                f"gold symbols: {', '.join(g for g in golds if g)}\n"
            )
        elif args.cmd == "circulars":
            run = archive_circulars(
                args.date_from, args.date_to, max_wait=args.max_wait
            )
            res = run.get("result") or {}
            circulars = res.get("circulars") or []
            _print(
                {
                    "run_id": run.get("run_id"),
                    "status": run.get("status"),
                    "steps": run.get("num_of_steps"),
                    "applied_date_filter": res.get("applied_date_filter"),
                    "reason_if_failed": res.get("reason_if_failed"),
                    "circulars": circulars,
                }
            )
            sys.stderr.write(
                f"{run.get('status')}: {len(circulars)} circulars "
                f"({run.get('num_of_steps')} agent steps)\n"
            )
        elif args.cmd == "search":
            results = search(args.query)
            _print({"query": args.query, "results": results})
    except TinyFishUnavailable as exc:
        sys.stderr.write(f"tinyfish unavailable: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
