"""TinyFish-backed live ingestion plane for arb-bound.

Isolated on purpose: nothing in ``arbbound`` imports this package, and this
package imports only ``arbbound.ingest`` for parsing. A failure here can never
change a published result.
"""

from .plane import (
    TinyFishUnavailable,
    archive_circulars,
    fetch_bhavcopy,
    fetch_page,
    live_gold_frame,
    search,
    wait_for_run,
    wallet,
)

__all__ = [
    "TinyFishUnavailable",
    "archive_circulars",
    "fetch_bhavcopy",
    "fetch_page",
    "live_gold_frame",
    "search",
    "wait_for_run",
    "wallet",
]
