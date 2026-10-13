"""TinyFish-backed live ingestion plane for arb-bound.

This module is the *only* place in the project that talks to the network. It
exists because of one hard-won fact: ``mcxindia.com`` returns HTTP 403 (Akamai)
to datacentre IPs, so the project could never ingest MCX data from a machine
like this one. A read proxy got us an HTML shell but never the JS-rendered
circular archive.

Verified 2026-10-13 against TinyFish's free Fetch endpoint:

* ``POST https://api.fetch.tinyfish.ai`` with ``{"urls": [...]}`` returned the
  **live dated bhavcopy** (4.9 MB of real JSON, all five gold contracts
  present) and the **circular listing** with real rows -- where curl gets an
  Access Denied page.
* Fetch ignores a ``?date=`` parameter: only *today's* bhavcopy is reachable.
  That is a real limitation, recorded here rather than papered over.
* The dated circular archive needed the **Agent** API, which drives a real
  browser: it set the archive's date filter and paged through the result. See
  ``archive_circulars``.

Nothing downstream of this module knows these calls happened. ``arbbound``
``ingest``/``analysis`` are untouched, which is the whole point: a failure here
degrades the project to exactly what it was, and every existing test still runs.

Rate/cost notes (verified from ``GET /v1/wallet``):
    TinyFish Fetch   $0.000 per url   -> free
    TinyFish Search  $0.000 per query -> free
    TinyFish Agent   $0.016 per step
    TinyFish Browser $0.002 per minute
    TinyFish Monitor $0.005 per run
So prefer Fetch/Search and treat Agent as the capped escalation path.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

FETCH_URL = "https://api.fetch.tinyfish.ai"
SEARCH_URL = "https://api.search.tinyfish.ai"
AGENT_RUN_URL = "https://agent.tinyfish.ai/v1/automation/run"
AGENT_ASYNC_URL = "https://agent.tinyfish.ai/v1/automation/run-async"
RUN_URL = "https://agent.tinyfish.ai/v1/runs/{run_id}"

MCX_BHAVCOPY = "https://www.mcxindia.com/market-data/bhavcopy"
MCX_CIRCULARS = "https://www.mcxindia.com/circulars/all-circulars"


class TinyFishUnavailable(RuntimeError):
    """Raised when the key is absent or the API rejects/refuses a request."""


def _key(explicit: str | None = None) -> str:
    """Resolve the API key without ever logging it."""
    val = explicit or os.environ.get("TINYFISH_API_KEY")
    if not val:
        raise TinyFishUnavailable(
            "TINYFISH_API_KEY is not set. Sign up via the HIH referral link, "
            "create a key at https://agent.tinyfish.ai/api-keys and export it."
        )
    return val


def _post_json(url: str, body: dict, key: str, timeout: float = 180.0) -> dict:
    """POST JSON and return the parsed body. Uses only the stdlib so the plane
    adds no dependency to the project."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # The key is secret; the status code and the server's own message are
        # not, so those are safe to surface.
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise TinyFishUnavailable(f"{url} -> HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # network, TLS, timeout
        raise TinyFishUnavailable(f"{url} unreachable: {exc}") from exc


def _get_json(url: str, key: str, timeout: float = 60.0) -> dict:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"X-API-Key": key}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise TinyFishUnavailable(f"{url} -> HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise TinyFishUnavailable(f"{url} unreachable: {exc}") from exc


def fetch_page(url: str, key: str | None = None) -> str:
    """Fetch one URL as clean text via the free Fetch endpoint."""
    body = {"urls": [url]}
    data = _post_json(FETCH_URL, body, _key(key))
    results = data.get("results") or []
    if not results:
        errors = data.get("errors") or []
        raise TinyFishUnavailable(f"Fetch returned no content for {url}: {errors}")
    return results[0].get("text", "")


def search(query: str, key: str | None = None) -> list[dict]:
    """Free structured web search."""
    import urllib.error
    import urllib.parse
    import urllib.request

    url = f"{SEARCH_URL}?{urllib.parse.urlencode({'query': query})}"
    req = urllib.request.Request(url, headers={"X-API-Key": _key(key)})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise TinyFishUnavailable(f"Search -> HTTP {exc.code}: {detail}") from exc
    return data.get("results", [])


def _extract_json_array(text: str) -> list:
    """Pull the bhavcopy JSON array out of whatever Fetch returned.

    Fetch usually hands back the raw JSON, but it occasionally returns an HTML
    wrapper (the page's ``<script>`` payload, or a partially rendered shell),
    and it also sometimes strips a trailing bracket. So: find the widest bracket
    span that actually contains bhavcopy rows, rather than assuming the whole
    response is JSON. Extracted on 2026-10-13 after the first live fetch failed
    this exact way.
    """
    best: list = []
    for start in [i for i, c in enumerate(text) if c == "["]:
        # Scan every '[' as a candidate start and keep the widest parseable span
        # that decodes to a non-empty list of objects with a Symbol field.
        for end in range(len(text), start, -1):
            if text[end - 1] != "]":
                continue
            try:
                rows = json.loads(text[start:end])
            except Exception:
                continue
            if (
                isinstance(rows, list)
                and rows
                and isinstance(rows[0], dict)
                and "Symbol" in rows[0]
            ):
                if len(rows) > len(best):
                    best = rows
            break
        if best:
            break
    return best


def fetch_bhavcopy(
    key: str | None = None,
    url: str = MCX_BHAVCOPY,
    attempts: int = 3,
    delay: float = 4.0,
) -> str:
    """Live MCX bhavcopy page as text.

    Retries because Fetch is not perfectly stable on this endpoint: it sometimes
    returns an HTML shell instead of the embedded JSON. Callers should use
    :func:`live_gold_frame`, which handles the extraction and the retry.
    Only *today's* bhavcopy is reachable; MCX ignores ``?date=`` on this URL.
    """
    last = ""
    for i in range(max(1, attempts)):
        try:
            raw = fetch_page(url, key)
        except TinyFishUnavailable:
            if i == attempts - 1:
                raise
            time.sleep(delay)
            continue
        last = raw
        if _extract_json_array(raw):
            return raw
        time.sleep(delay)
    return last


def _agent_run(
    goal: str, key: str, url: str = MCX_CIRCULARS, schema: dict | None = None
) -> dict:
    """Run one synchronous Agent automation."""
    body: dict[str, Any] = {"url": url, "goal": goal}
    if schema:
        body["output_schema"] = schema
    return _post_json(AGENT_RUN_URL, body, key, timeout=1200.0)


def _agent_run_async(
    goal: str, key: str, url: str = MCX_CIRCULARS, schema: dict | None = None
) -> str:
    body: dict[str, Any] = {"url": url, "goal": goal}
    if schema:
        body["output_schema"] = schema
    data = _post_json(AGENT_ASYNC_URL, body, key, timeout=120.0)
    return data.get("run_id", "")


def wait_for_run(
    run_id: str, key: str | None = None, poll: float = 20.0, max_wait: float = 1800.0
) -> dict:
    """Poll a run until it reaches a terminal state."""
    deadline = time.time() + max_wait
    last: dict = {}
    while time.time() < deadline:
        last = _get_json(RUN_URL.format(run_id=run_id), _key(key))
        status = last.get("status")
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            return last
        time.sleep(poll)
    raise TinyFishUnavailable(
        f"run {run_id} still {last.get('status')} after {max_wait}s"
    )


def archive_circulars(
    date_from: str,
    date_to: str,
    key: str | None = None,
    poll: float = 20.0,
    max_wait: float = 1800.0,
) -> dict:
    """Date-filter MCX's circular archive and return the structured result.

    This is the capability that was previously unreachable. The archive's
    date filter is applied client-side, so Fetch sees only the default page
    (the most recent circulars); the Agent API has to drive a real browser to
    set From/To dates, click Show, and page through the results.

    Returns the full run document, including ``result["circulars"]`` and the
    run metadata needed to prove provenance.

    Verified 2026-10-13: 01/10/2024 -> 31/12/2024 returned 204 circulars across
    14 result pages in 115 steps.
    """
    k = _key(key)
    schema = {
        "type": "object",
        "properties": {
            "applied_date_filter": {"type": "boolean"},
            "circulars": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "category": {"type": "string"},
                        "title": {"type": "string"},
                        "circular_no": {"type": "string"},
                    },
                    "required": ["date", "category"],
                },
            },
            "reason_if_failed": {"type": "string", "nullable": True},
        },
        "required": ["applied_date_filter", "circulars"],
    }
    goal = (
        f"Set the From Date field to {date_from} and the To Date field to "
        f"{date_to}, then click the Show button. Wait for the circulars table "
        "to refresh. Page through every page of results and list every circular "
        "with its date, category, title and circular number. If the date fields "
        "cannot be found or the table does not change, set applied_date_filter "
        "to false and explain why in reason_if_failed."
    )
    run_id = _agent_run_async(goal, k, MCX_CIRCULARS, schema)
    if not run_id:
        raise TinyFishUnavailable("archive_circulars: no run_id returned")
    return wait_for_run(run_id, k, poll=poll, max_wait=max_wait)


def wallet(key: str | None = None) -> dict:
    """Current balance and rates -- proves the key works and prices the plan."""
    return _get_json("https://agent.tinyfish.ai/v1/wallet", _key(key))


def live_gold_frame(
    key: str | None = None,
):
    """Parse the live bhavcopy into the same tidy frame the engine consumes.

    This is the seam the whole project hangs on. The extraction and
    normalisation are ``arbbound.ingest``'s own functions -- *unchanged* -- so a
    live row and a committed CSV/JSON row go through identical logic. Nothing
    about parsing was reimplemented here.

    Returns ``(frame, source)`` where ``source`` is a provenance string.
    """
    import tempfile

    from arbbound.ingest import extract_bhavcopy_array, load_json_bhavcopy

    raw = fetch_bhavcopy(key)
    # The project's own extractor, used verbatim. It locates the array by the
    # row marker and matches brackets, so it survives an HTML wrapper.
    try:
        rows = extract_bhavcopy_array(raw)
    except ValueError as exc:
        raise TinyFishUnavailable(
            f"live bhavcopy: {exc} ({len(raw)} bytes returned)"
        ) from exc
    if not rows:
        raise TinyFishUnavailable("live bhavcopy: extractor returned no rows")

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(rows, fh)
        tmp = fh.name
    try:
        frame = load_json_bhavcopy(tmp)
    finally:
        Path(tmp).unlink(missing_ok=True)

    if frame.empty:
        raise TinyFishUnavailable("live bhavcopy: normaliser returned an empty frame")
    return frame, f"tinyfish-live:{MCX_BHAVCOPY}"
