"""Guards for the in-browser playground.

The playground is the strongest claim in this project: that the pipeline is real
code which runs on input it has never seen. These tests keep that claim honest.

They check three things:

1. the page actually embeds this package's *current* source, so it cannot drift
   from what the command line runs;
2. the sample input travels intact (it is gzipped) and contains a genuinely
   analysable bhavcopy - not a placeholder;
3. the wiring is present: a run handler that clears stale results, a rejection
   path, and links from the static report to the playground.
"""

from __future__ import annotations

import base64
import gzip
import json
import re
from pathlib import Path

import pytest

from arbbound.playground import PYODIDE_VERSION, build_playground

PKG = Path("arbbound")


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    out = tmp_path_factory.mktemp("pg") / "playground.html"
    build_playground(
        PKG,
        Path("data/fixture_gold_2023-2026.csv").read_text(),
        out,
        sample_label="test sample",
    )
    return out.read_text()


def _embedded_sources(page: str) -> dict[str, str]:
    m = re.search(r"const SOURCES = (\{.*?\});\nconst SAMPLE_GZ", page, re.S)
    assert m, "could not find embedded sources block"
    return json.loads(m.group(1))


def _embedded_sample(page: str) -> str:
    m = re.search(r"const SAMPLE_GZ = \"([A-Za-z0-9+/=]+)\";", page)
    assert m, "could not find embedded sample"
    return gzip.decompress(base64.b64decode(m.group(1))).decode("utf-8")


# --------------------------------------------- the page ships the real source


def test_embeds_every_analysis_module(page):
    src = _embedded_sources(page)
    for name in ("contracts.py", "bound.py", "ingest.py", "analysis.py", "cli.py", "report.py"):
        assert name in src, f"missing {name} from the playground"


def test_embedded_source_matches_the_repository(page):
    """If the embedded copy drifts from the repo, the demo lies about what runs."""
    src = _embedded_sources(page)
    for name, text in src.items():
        on_disk = (PKG / name).read_text()
        assert text == on_disk, f"{name} in the page is stale relative to the repo"


def test_pyodide_version_is_pinned(page):
    """An unpinned runtime could change behaviour under us."""
    assert f"v{PYODIDE_VERSION}/full/pyodide.js" in page
    assert PYODIDE_VERSION.count(".") == 2


# ------------------------------------------------ the sample is genuinely real


def test_embedded_sample_is_a_real_bhavcopy(page):
    csv = _embedded_sample(page)
    lines = csv.strip().splitlines()
    assert len(lines) > 5_000, "sample looks truncated"
    header = lines[0].split(",")
    for col in ("date", "symbol", "close"):
        assert col in header, f"sample missing {col}"
    # All four modelled contracts must survive whatever sampling was applied.
    for sym in ("GOLDGUINEA", "GOLDM", "GOLDPETAL", "GOLDTEN"):
        assert sym in csv, f"sample dropped {sym}"


def test_page_is_byte_for_byte_reproducible(tmp_path):
    """Rebuilding from the same input must produce identical bytes.

    The gzip header carries an mtime field; leaving it at the wall clock
    makes the committed page differ from a fresh build for no real reason,
    which turns the CI drift check into noise and undermines the claim that
    every published byte is generated from the input.
    """
    csv_text = Path("data/fixture_gold_2023-2026.csv").read_text()
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    build_playground(PKG, csv_text, first, sample_label="test sample")
    build_playground(PKG, csv_text, second, sample_label="test sample")
    assert first.read_bytes() == second.read_bytes()


def test_page_loads_nothing_but_the_pinned_runtime(page):
    """No API keys, no server calls - only the pinned CDN runtime.

    Plain hyperlinks (to the repo, to the static report) are fine: they are
    navigation, not resources the analysis depends on. What must not exist is an
    external *script* or a runtime *fetch* to a data endpoint.
    """
    scripts = re.findall(r'<script[^>]+src="(https?://[^"]+)"', page)
    assert scripts == [f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/pyodide.js"], scripts

    # No outbound data calls in the page's own JavaScript.
    assert not re.search(r'fetch\(\s*["\']https?://', page), "page makes an external fetch"
    assert "XMLHttpRequest" not in page
    for bad in ("api_key", "apiKey", "sk-", "Bearer "):
        assert bad not in page


# -------------------------------------------------------- the wiring is honest


def test_run_handler_clears_stale_results(page):
    """A failed run must not leave the previous verdict on screen."""
    assert '$("out").srcdoc = "";' in page
    assert 'metaEl.textContent = "";' in page


def test_rejection_path_exists_and_hides_tracebacks(page):
    assert "input rejected" in page
    assert 'msg.split("\\n")' in page, "no traceback trimming"


def test_static_report_links_to_the_playground():
    from arbbound.report import render

    html = render(json.loads(Path("docs/report.json").read_text()))
    assert 'href="playground.html"' in html


def test_ingest_rejects_non_bhavcopy_with_a_clear_message():
    """The library itself must explain the problem, not raise a bare KeyError."""
    import pandas as pd

    from arbbound.ingest import load_csv_bhavcopy

    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write("not,a,bhavcopy\n1,2,3\n")
        path = fh.name
    with pytest.raises(ValueError, match="Symbol"):
        load_csv_bhavcopy(path)