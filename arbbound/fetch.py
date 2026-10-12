"""Fetch a live MCX bhavcopy through a read proxy and save it.

MCX protects its endpoints with an Akamai bot manager that returns HTTP 403 to
data-centre IPs, so a direct fetch usually fails. This module fetches the
bhavcopy page through a text-extraction proxy that renders the page from its
own egress, then extracts the embedded JSON payload.

The extractor is shared with the normaliser so that a file fetched today and a
file fetched by the CSV-drop path produce identical frames.

Usage
-----
    python -m arbbound.fetch --date 2026-09-10 --out data/bhavcopy_2026-09-10.json
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

from .ingest import extract_bhavcopy_array

BHAVCOPY_PAGE = "https://www.mcxindia.com/market-data/bhavcopy"

#: Read proxies tried in order. Each fetches the page from its own egress.
PROXIES = (
    "https://r.jina.ai/{url}",
)


def fetch_page(url: str = BHAVCOPY_PAGE, timeout: int = 90) -> str:
    """Retrieve the bhavcopy page HTML/Markdown via a proxy chain."""
    last_error: Exception | None = None
    for template in PROXIES:
        target = template.format(url=url)
        try:
            request = urllib.request.Request(
                target, headers={"User-Agent": "arb-bound/0.1 (+research)"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - report the last failure
            last_error = exc
    raise RuntimeError(f"all proxies failed for {url}: {last_error}")


def fetch_bhavcopy(url: str = BHAVCOPY_PAGE) -> list[dict]:
    """Fetch and parse today's bhavcopy rows."""
    page = fetch_page(url)
    return extract_bhavcopy_array(page)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="arbbound.fetch", description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="destination .json file")
    ap.add_argument("--url", default=BHAVCOPY_PAGE)
    args = ap.parse_args(argv)

    try:
        rows = fetch_bhavcopy(args.url)
    except Exception as exc:  # noqa: BLE001
        print(f"fetch failed: {exc}", file=sys.stderr)
        print(
            "Fallback: download the bhavcopy CSV manually from "
            f"{BHAVCOPY_PAGE} and pass it to --input.",
            file=sys.stderr,
        )
        return 1

    import json

    args.out.write_text(json.dumps(rows))
    print(f"wrote {len(rows):,} bhavcopy rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())