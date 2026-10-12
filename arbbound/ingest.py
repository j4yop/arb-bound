"""Ingest MCX bhavcopy data and normalise it to rupees per gram of fine gold.

Input is either the live JSON the MCX bhavcopy page embeds, or a CSV of already
extracted rows. The point of this module is that no downstream analysis ever
sees a raw MCX row: symbols are stripped, dates parsed, contracts that did not
trade are flagged, and every price is expressed per gram of fine gold.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .contracts import THIN_OI_LOTS, THIN_VOLUME_LOTS, spec_for

# MCX packs the whole bhavcopy into the page as a JSON array whose first
# element has a null "sLTT" field. We find the enclosing brackets rather than
# relying on a fragile marker.
_ROW_MARKER = '{"sLTT"'


def extract_bhavcopy_array(page_text: str) -> list[dict]:
    """Pull the embedded bhavcopy JSON array out of an MCX page.

    Raises
    ------
    ValueError
        If no bhavcopy rows can be located in the text.
    """
    start = page_text.find(_ROW_MARKER)
    if start == -1:
        raise ValueError("no bhavcopy rows found in page")

    opening = page_text.rfind("[", 0, start)
    if opening == -1:
        raise ValueError("bhavcopy rows found but not inside a JSON array")

    depth = 0
    for idx in range(opening, len(page_text)):
        ch = page_text[idx]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(page_text[opening : idx + 1])
    raise ValueError("unterminated bhavcopy JSON array")


def load_json_bhavcopy(path: str | Path) -> pd.DataFrame:
    """Load an MCX bhavcopy JSON dump (array of row dicts) into a frame."""
    rows = json.loads(Path(path).read_text())
    frame = pd.DataFrame(rows)
    return _normalise_frame(frame)


def load_csv_bhavcopy(path: str | Path) -> pd.DataFrame:
    """Load an already-flattened CSV of bhavcopy rows.

    Expects MCX's native column names but tolerates snake_case variants that
    common parsers produce.
    """
    frame = pd.read_csv(path)
    renames = {
        "Symbol": "Symbol",
        "ExpiryDate": "ExpiryDate",
        "Open": "Open",
        "High": "High",
        "Low": "Low",
        "Close": "Close",
        "PreviousClose": "PreviousClose",
        "Volume": "Volume",
        "OpenInterest": "OpenInterest",
        "InstrumentName": "InstrumentName",
        "symbol": "Symbol",
        "date": "Date",
        "expiry_date": "ExpiryDate",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "prev_close": "PreviousClose",
        "previous_close": "PreviousClose",
        "volume_lots": "Volume",
        "open_interest_lots": "OpenInterest",
    }
    frame = frame.rename(columns={k: v for k, v in renames.items() if k in frame.columns})
    return _normalise_frame(frame)


def _parse_mcx_date(value: object) -> pd.Timestamp:
    """Parse MCX's two date formats.

    Requests and CSV exports use ``DD/MM/YYYY``; the API response uses
    ``MM/DD/YYYY``. Expiries use a compact ``04SEP2026`` form.
    """
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return pd.Timestamp(pd.to_datetime(text, format=fmt))
        except (ValueError, TypeError):
            continue
    # Compact expiry form, e.g. 04SEP2026
    m = re.fullmatch(r"(\d{2})([A-Z]{3})(\d{4})", text)
    if m:
        return pd.Timestamp(f"{m.group(3)}-{m.group(2)}-{m.group(1)}")
    raise ValueError(f"unrecognised MCX date: {value!r}")


def _normalise_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Clean raw rows and reduce them to the gold futures we model."""
    if frame.empty:
        raise ValueError("bhavcopy contained no rows")

    frame = frame.copy()
    frame["symbol"] = frame["Symbol"].astype(str).str.strip()

    # Options rows share the Symbol of their underlying future, so they must be
    # filtered out before anything downstream assumes a futures row.
    if "InstrumentName" in frame.columns:
        instrument = frame["InstrumentName"].astype(str).str.strip().str.upper()
        frame = frame[instrument == "FUTCOM"].copy()

    frame["date"] = frame["Date"].map(_parse_mcx_date)
    frame["expiry"] = frame["ExpiryDate"].map(_parse_mcx_date)

    for col in ("Open", "High", "Low", "Close", "PreviousClose"):
        frame[col] = pd.to_numeric(frame.get(col), errors="coerce")

    frame["Volume"] = pd.to_numeric(frame.get("Volume"), errors="coerce").fillna(0.0)
    frame["OpenInterest"] = pd.to_numeric(
        frame.get("OpenInterest"), errors="coerce"
    ).fillna(0.0)

    # Keep only contracts we have a spec for.
    frame = frame[frame["symbol"].isin(set(_spec_symbols()))].copy()
    if frame.empty:
        raise ValueError("bhavcopy contained no rows for the modelled contracts")

    frame["lot_grams"] = frame["symbol"].map(lambda s: spec_for(s).lot_grams)
    frame["quote_grams"] = frame["symbol"].map(lambda s: spec_for(s).quote_grams)
    frame["purity"] = frame["symbol"].map(lambda s: spec_for(s).purity)

    # The only price definition used anywhere in this project.
    frame["px_per_g_fine"] = frame["Close"] / frame["quote_grams"] / frame["purity"]

    frame["days_to_expiry"] = (frame["expiry"] - frame["date"]).dt.days

    # A row is not a trade if nothing traded or the exchange printed zeroes.
    frame["no_trade"] = (
        (frame["Volume"] <= 0)
        | frame["Open"].isna()
        | (frame["Open"] == 0)
        | frame["Close"].isna()
        | (frame["Close"] == 0)
    )
    frame["is_thin"] = (frame["Volume"] < THIN_VOLUME_LOTS) | (
        frame["OpenInterest"] < THIN_OI_LOTS
    )

    frame = frame.sort_values(["symbol", "expiry", "date"]).reset_index(drop=True)
    return frame[
        [
            "date",
            "symbol",
            "expiry",
            "days_to_expiry",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "OpenInterest",
            "lot_grams",
            "quote_grams",
            "purity",
            "px_per_g_fine",
            "no_trade",
            "is_thin",
        ]
    ]


def _spec_symbols() -> list[str]:
    from .contracts import CONTRACTS

    return list(CONTRACTS)


def matched_basis(
    bhavcopy: pd.DataFrame, max_maturity_gap_days: int = 7, max_dte: int = 120
) -> pd.DataFrame:
    """Compute per-pair basis **at matched maturity**.

    Why this exists
    ---------------
    A naive "median price of every listed expiry" per contract is wrong for this
    problem, and dangerously so. The four gold contracts expire on *offset*
    calendars - GOLDM on the 3rd-5th, GOLDPETEN/GOLDGUINEA/GOLDTEN on the
    27th-31st - and MCX lists expiries out to 6+ months. Comparing a median
    across all of them mixes the **term structure** into the cross-contract
    basis: a far-dated leg carries a different carry than a near-dated leg, and
    the resulting "spread" is mostly calendar, not dislocation.

    The brief is explicit about this: track contracts by expiry date rather
    than a continuous near-month series, because rolling creates artificial
    jumps.

    The fix
    -------
    For each pair and each trading day, select the expiry of each contract
    whose days-to-expiry is *closest* to its partner, and keep the
    observation only when:

    * the two legs are within ``max_maturity_gap_days`` of each other, and
    * both legs are inside ``max_dte`` (near enough that carry is comparable),
    * both legs actually traded.

    Returns one column per pair in basis points, ``10000 * ln(px_a / px_b)``,
    with ``NaN`` wherever a defensible match does not exist. Gaps are left as
    gaps rather than interpolated, so a break in the series is a real absence
    of comparable data, not a smoothed artefact.
    """
    import math

    from .contracts import pairs

    traded = bhavcopy[
        (~bhavcopy["no_trade"]) & (bhavcopy["days_to_expiry"] <= max_dte)
    ]

    out: dict[str, pd.Series] = {}
    for a, b in pairs():
        left = traded[traded["symbol"] == a]
        right = traded[traded["symbol"] == b]

        rows = []
        for date in sorted(set(left["date"]) & set(right["date"])):
            la = left[left["date"] == date]
            rb = right[right["date"] == date]
            if la.empty or rb.empty:
                rows.append((date, math.nan))
                continue

            # Choose the maturity-matched leg on each side.
            best = None
            for _, ra in la.iterrows():
                for _, rbb in rb.iterrows():
                    gap = abs(ra["days_to_expiry"] - rbb["days_to_expiry"])
                    if best is None or gap < best[0]:
                        best = (gap, ra, rbb)
            gap, ra, rbb = best
            if gap > max_maturity_gap_days:
                rows.append((date, math.nan))
            else:
                rows.append(
                    (date, 1e4 * math.log(ra["px_per_g_fine"] / rbb["px_per_g_fine"]))
                )

        series = pd.Series(
            dict(rows), name=f"{a}/{b}", dtype=float
        ).sort_index()
        out[f"{a}/{b}"] = series

    frame = pd.DataFrame(out).sort_index()
    return frame


def daily_basis(bhavcopy: pd.DataFrame) -> pd.DataFrame:
    """Naive per-pair basis across all listed expiries.

    Retained for comparison and regression testing only. **Do not use for
    conclusions** - it confounds cross-contract dislocation with term
    structure. ``matched_basis`` is the correct entry point.
    """
    import math

    from .contracts import pairs

    traded = bhavcopy[~bhavcopy["no_trade"]]
    out = {}
    for a, b in pairs():
        left = traded[traded["symbol"] == a].groupby("date")["px_per_g_fine"].median()
        right = traded[traded["symbol"] == b].groupby("date")["px_per_g_fine"].median()
        joined = pd.concat([left.rename("a"), right.rename("b")], axis=1).dropna()
        out[f"{a}/{b}"] = 1e4 * (joined["a"] / joined["b"]).map(math.log)
    return pd.DataFrame(out).sort_index()


def reference_price(bhavcopy: pd.DataFrame) -> float:
    """Median per-gram fine-gold price across all traded contract-days.

    Used to convert rupee-denominated bounds into basis points. Taking the
    median over the whole sample rather than a single day keeps the conversion
    stable across the multi-year window and avoids anchoring the bound to an
    unusual price regime.
    """
    traded = bhavcopy[~bhavcopy["no_trade"]]
    if traded.empty:
        raise ValueError("cannot derive a reference price: no traded rows")
    return float(traded["px_per_g_fine"].median())