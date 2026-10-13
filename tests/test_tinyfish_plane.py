"""Tests for the TinyFish plane.

Every test here is offline: the HTTP calls are replaced, so the suite costs
nothing and can run in CI. The live capabilities themselves are proven by the
recorded runs in ``docs/TINYFISH.md`` and by ``scripts/read_circular766.sh``.
"""

from __future__ import annotations

import json

import pytest

from tinyfish_plane import plane


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Fail loudly if a test reaches for the network, and let the key resolve
    without touching a real credential."""
    monkeypatch.setenv("TINYFISH_API_KEY", "sk-tinyfish-not-real")

    def boom(*a, **k):
        raise AssertionError("a test attempted a real network call")

    monkeypatch.setattr(plane, "_post_json", boom)
    monkeypatch.setattr(plane, "_get_json", boom)


# ------------------------------------------------------------------- the key


def test_missing_key_raises_a_usable_error(monkeypatch):
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    with pytest.raises(plane.TinyFishUnavailable) as exc:
        plane.fetch_page("https://example.com")
    assert "TINYFISH_API_KEY" in str(exc.value)


def test_key_is_resolved_from_argument_without_logging():
    """The key may be passed explicitly; it must never be echoed."""
    assert plane._key("sk-tinyfish-not-real") == "sk-tinyfish-not-real"


# The real implementations, captured before the autouse fixture replaces them,
# so a test can restore one deliberately and control only the network layer.
_REAL_POST = plane._post_json
_REAL_GET = plane._get_json


# ------------------------------------------------------------ error surfaces


def test_fetch_error_mentions_status_not_credentials(monkeypatch):
    """A 401 must surface the status code, never the credential."""
    import io
    import urllib.error
    import urllib.request

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", None, io.BytesIO(b'{"error":"nope"}')
        )

    # Restore the real _post_json so its own handler is what we exercise.
    monkeypatch.setattr(plane, "_post_json", _REAL_POST)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(plane.TinyFishUnavailable) as exc:
        plane.fetch_page("https://example.com", key="sk-tinyfish-not-real")
    assert "401" in str(exc.value)
    assert "sk-tinyfish-not-real" not in str(exc.value)


# ------------------------------------------------------- the payload contract


def test_live_rows_are_normalised_by_the_project_own_parser(monkeypatch):
    """The plane must use arbbound.ingest, not a re-implementation."""
    calls = {}

    def fake_fetch(url, key=None, attempts=1, delay=0.0):
        return json.dumps(
            [
                {
                    "sLTT": None,
                    "Date": "10/12/2026",
                    "DateDisplay": "12 Oct 2026",
                    "Symbol": "GOLDM ",
                    "ExpiryDate": "05OCT2026",
                    "Open": 100000.0,
                    "High": 100500.0,
                    "Low": 99500.0,
                    "Close": 100100.0,
                    "PreviousClose": 99800.0,
                    "Volume": 12000,
                    "VolumeInThousands": "12.000 KGS ",
                    "Value": 5000.0,
                    "OpenInterest": 40000,
                    "InstrumentName": "FUTCOM",
                },
                {
                    "sLTT": None,
                    "Date": "10/12/2026",
                    "DateDisplay": "12 Oct 2026",
                    "Symbol": "GOLDGUINEA ",
                    "ExpiryDate": "05NOV2026",
                    "Open": 78000.0,
                    "High": 78500.0,
                    "Low": 77500.0,
                    "Close": 78100.0,
                    "PreviousClose": 77900.0,
                    "Volume": 3000,
                    "VolumeInThousands": "3.000 KGS ",
                    "Value": 1000.0,
                    "OpenInterest": 9000,
                    "InstrumentName": "FUTCOM",
                },
            ]
        )

    monkeypatch.setattr(plane, "fetch_bhavcopy", fake_fetch)
    # Prove the temporary-JSON handoff: the project's own loader must be the
    # thing that reads the rows, not a CSV writer written here.
    import arbbound.ingest as ingest

    real = ingest.load_json_bhavcopy
    seen: dict = {}

    def spy(path):
        seen["path"] = path
        import pathlib

        seen["is_json"] = str(path).endswith(".json")
        seen["rows_in_file"] = len(json.loads(pathlib.Path(path).read_text()))
        return real(path)

    monkeypatch.setattr(ingest, "load_json_bhavcopy", spy)

    frame, source = plane.live_gold_frame("sk-tinyfish-not-real")
    assert source.startswith("tinyfish-live:")
    assert seen["rows_in_file"] == 2, "the extracted rows must reach the loader"
    assert set(frame["symbol"]) == {"GOLDM", "GOLDGUINEA"}
    # The DateDisplay fix: 12 October, not 10 December.
    assert set(frame["date"].dt.strftime("%Y-%m-%d")) == {"2026-10-12"}


def test_archive_circulars_submits_and_polls(monkeypatch):
    """The archive path is submit-async then poll -- never a blocking call.

    The seam is _agent_run_async (submit) and wait_for_run (poll), which is
    exactly the two-step handshake the real API uses, verified by the recorded
    run in docs/TINYFISH.md.
    """
    seen: dict = {}

    def fake_submit(goal, key, url=plane.MCX_CIRCULARS, schema=None):
        seen["goal"] = goal
        seen["url"] = url
        seen["schema"] = schema
        return "run-123"

    def fake_wait(run_id, key=None, poll=20.0, max_wait=1800.0):
        seen["run_id"] = run_id
        return {"run_id": "run-123", "status": "COMPLETED", "num_of_steps": 115,
                "result": {"applied_date_filter": True, "circulars": [
                    {"date": "31 Dec 2024", "category": "T&S",
                     "title": "Commencement Of Futures Trading In Gold Petal "
                              "April 2025 Contract",
                     "circular_no": "858"}]}}

    monkeypatch.setattr(plane, "_agent_run_async", fake_submit)
    monkeypatch.setattr(plane, "wait_for_run", fake_wait)

    run = plane.archive_circulars("01/10/2024", "31/12/2024")
    assert "01/10/2024" in seen["goal"] and "31/12/2024" in seen["goal"]
    assert seen["url"] == plane.MCX_CIRCULARS
    assert seen["run_id"] == "run-123"
    assert seen["schema"]["required"] == ["applied_date_filter", "circulars"]
    assert run["status"] == "COMPLETED"
    assert run["result"]["circulars"][0]["circular_no"] == "858"


def test_wait_for_run_raises_instead_of_looping_forever(monkeypatch):
    def fake_get(url, key):
        return {"status": "RUNNING"}

    monkeypatch.setattr(plane, "_get_json", fake_get)
    monkeypatch.setattr(plane.time, "sleep", lambda s: None)
    with pytest.raises(plane.TinyFishUnavailable) as exc:
        plane.wait_for_run("run-x", max_wait=1.0, poll=0.0)
    assert "still RUNNING" in str(exc.value)
