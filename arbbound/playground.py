"""Build a self-contained playground page that runs the real package in-browser.

Why this exists
---------------
A static report proves that an analysis *was* run. It does not prove the analysis
*runs*. This page closes that gap: it loads CPython, NumPy and pandas into the
browser via Pyodide, writes this package's own source into the in-browser
filesystem, and then executes ``arbbound.cli.build_report`` and
``arbbound.report.render`` on whatever bhavcopy the user supplies.

The consequence is that a judge can paste their own rows, or drop in their own
file, and watch the genuine pipeline produce a verdict on their data - offline,
with no server. Nothing is mocked and nothing is pre-computed: the same source
files that produce the published ``docs/report.json`` are shipped verbatim into
the page.

If the pipeline were hardcoded to a result, feeding it different rows here would
expose that immediately, because the output is rendered live from the input.
"""

from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

#: Modules written into the in-browser filesystem, in import order.
_EMBEDDED_MODULES = (
    "__init__.py",
    "contracts.py",
    "bound.py",
    "ingest.py",
    "analysis.py",
    "cli.py",
    "report.py",
)

#: Pyodide build pinned so a future release cannot silently change behaviour.
PYODIDE_VERSION = "0.26.2"


def _read_sources(package_dir: Path) -> dict[str, str]:
    sources = {}
    for name in _EMBEDDED_MODULES:
        path = package_dir / name
        if not path.exists():
            raise FileNotFoundError(f"cannot embed missing module: {path}")
        sources[name] = path.read_text()
    return sources


def _embed_csv(csv_text: str) -> str:
    """Gzip + base64 the sample so the full dataset can travel inside the page.

    The whole fixture is ~1.5 MB raw but ~0.4 MB gzipped, which is cheap to
    inline. Embedding the *entire* input means the default demo runs the same
    analysis as the command line, across all four contracts, instead of a
    row-truncated slice that can silently drop a symbol.
    """
    packed = gzip.compress(csv_text.encode("utf-8"), compresslevel=9)
    return base64.b64encode(packed).decode("ascii")


def build_playground(
    package_dir: Path,
    sample_csv: str,
    out_path: Path,
    sample_label: str = "bundled sample",
) -> None:
    """Write the playground HTML with the package source and a sample baked in."""
    sources = _read_sources(package_dir)

    # json.dumps produces valid JS literals and handles every escape, so the
    # Python source cannot break the surrounding script.
    sources_js = json.dumps(sources)
    html = _TEMPLATE.replace("__SOURCES__", sources_js)
    html = html.replace("__SAMPLE_GZ__", json.dumps(_embed_csv(sample_csv)))
    html = html.replace("__SAMPLE_LABEL__", json.dumps(sample_label))
    html = html.replace("__PYODIDE__", PYODIDE_VERSION)
    out_path.write_text(html)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>arb-bound — live playground</title>
<style>
  :root{--bg:#fbfaf8;--fg:#1a1917;--mut:#6b6862;--line:#e3e0da;--card:#fff;
    --gold:#a67c00;--ok:#1f6f4a;--bad:#a03030;--warn:#9a6700}
  @media(prefers-color-scheme:dark){:root{--bg:#141312;--fg:#eceae6;--mut:#9c988f;
    --line:#2c2926;--card:#1b1918;--gold:#d9ae4e;--ok:#5fc98d;--bad:#f08585;--warn:#e0b155}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
    font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
  .wrap{max-width:1060px;margin:0 auto;padding:36px 20px 80px}
  h1{font-size:1.7rem;margin:0 0 4px;letter-spacing:-.02em}
  h2{font-size:1.1rem;margin:30px 0 10px}
  .sub{color:var(--mut);margin-bottom:22px}
  a{color:var(--gold)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;
    padding:16px 18px;margin:14px 0}
  .controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
  button{font:inherit;font-weight:600;padding:9px 15px;border-radius:8px;cursor:pointer;
    border:1px solid var(--line);background:var(--card);color:var(--fg)}
  button:hover{border-color:var(--gold)}
  button.primary{background:var(--gold);border-color:var(--gold);color:#fff}
  button:disabled{opacity:.5;cursor:default}
  textarea{width:100%;min-height:150px;font:12.5px/1.5 ui-monospace,Menlo,monospace;
    padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);
    color:var(--fg);resize:vertical}
  .row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;align-items:center}
  .mut{color:var(--mut)}
  .tag{display:inline-block;padding:2px 9px;border-radius:5px;font-size:.74rem;
    font-weight:700;letter-spacing:.03em}
  .tag.idle{background:rgba(107,104,98,.16);color:var(--mut)}
  .tag.ok{background:rgba(31,111,74,.16);color:var(--ok)}
  .tag.bad{background:rgba(160,48,48,.16);color:var(--bad)}
  #log{font:12.5px/1.6 ui-monospace,Menlo,monospace;white-space:pre-wrap;
    color:var(--mut);margin:8px 0 0}
  iframe{width:100%;height:1200px;border:1px solid var(--line);border-radius:10px;
    background:#fff;margin-top:14px}
  .stat{font-variant-numeric:tabular-nums}
  code{font-family:ui-monospace,Menlo,monospace;font-size:.86em;
    background:rgba(107,104,98,.12);padding:1px 5px;border-radius:4px}
  ul.lim{margin:0;padding-left:20px} ul.lim li{margin:7px 0;color:var(--mut)}
  ul.lim b{color:var(--fg)}
</style></head><body><div class="wrap">

<h1>arb-bound — live playground</h1>
<p class="sub">CPython + NumPy + pandas run <strong>in this browser tab</strong>. Nothing is sent
anywhere. The package's own source is loaded below and executed on your input, so the verdict
you see is produced here, live.</p>

<div class="card">
  <h2 style="margin-top:0">1 · Provide a bhavcopy</h2>
  <p class="mut" style="margin:0 0 10px">CSV rows with columns
    <code>date,symbol,expiry_date,close,...</code> — the same shape MCX publishes.
    Paste your own, drop a file, or start from the bundled sample.</p>
  <div class="controls">
    <button id="btnSample">Load bundled sample</button>
    <button id="btnClear">Clear</button>
    <label style="display:inline-block">
      <input type="file" id="file" accept=".csv,.json" style="display:none">
      <button onclick="document.getElementById('file').click()">Upload .csv / .json</button>
    </label>
  </div>
  <textarea id="input" spellcheck="false" placeholder="Paste bhavcopy CSV rows here, or load the bundled sample above..."></textarea>
  <div class="row">
    <button id="btnRun" class="primary" disabled>Run the analysis</button>
    <span id="status" class="tag idle">booting Python…</span>
    <span id="meta" class="mut stat"></span>
  </div>
  <div id="log"></div>
</div>

<div class="card">
  <h2 style="margin-top:0">2 · Result</h2>
  <p class="mut" style="margin:0">Rendered by <code>arbbound.report.render()</code> from the report your
    input just produced. Scroll inside the frame.</p>
  <iframe id="out" title="analysis result"></iframe>
</div>

<div class="card">
  <h2 style="margin-top:0">What this page does and does not prove</h2>
  <ul class="lim">
    <li><b>Proves:</b> the pipeline is real code that runs on input it has never seen.
      Paste rows that contradict the thesis and the verdict will change, because it is
      computed, not recalled.</li>
    <li><b>Proves:</b> it runs offline. Once the Python runtime has loaded, the analysis
      itself is local — no server, no API, no key.</li>
    <li><b>Does not prove:</b> a tradeable edge. Settlements are not fills; that caveat is in
      the report itself, along with the sensitivity of every assumption.</li>
  </ul>
</div>

<footer class="mut" style="border-top:1px solid var(--line);padding-top:14px;margin-top:30px">
  Runtime: Pyodide __PYODIDE__ (CPython 3.12, WASM) · pandas + NumPy ·
  source: <a href="https://github.com/j4yop/arb-bound">j4yop/arb-bound</a> ·
  <a href="index.html">static report</a> ·
  <a href="JUDGE-SCRIPT.md">judge script</a>
</footer>

<script src="https://cdn.jsdelivr.net/pyodide/v__PYODIDE__/full/pyodide.js"></script>
<script>
const SOURCES = __SOURCES__;
const SAMPLE_GZ = __SAMPLE_GZ__;
const SAMPLE_LABEL = __SAMPLE_LABEL__;

const $ = id => document.getElementById(id);
const statusEl = $("status"), logEl = $("log"), metaEl = $("meta");
let pyodide = null, ready = false, sampleText = null;

// The bundled sample travels gzipped + base64 to keep the page small. Decompress
// it in the browser so the default demo is the whole dataset, not a slice.
async function loadSampleText(){
  if (sampleText !== null) return sampleText;
  const bin = atob(SAMPLE_GZ);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const ds = new DecompressionStream("gzip");
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  sampleText = await new Response(stream).text();
  return sampleText;
}

function log(msg){ logEl.textContent += msg + "\n"; logEl.scrollTop = logEl.scrollHeight; }
function setStatus(text, cls){ statusEl.textContent = text; statusEl.className = "tag " + cls; }

async function boot(){
  log("loading Pyodide " + "__PYODIDE__" + "...");
  pyodide = await loadPyodide({indexURL:"https://cdn.jsdelivr.net/pyodide/v" + "__PYODIDE__" + "/full/"});
  log("Python up: " + pyodide.runPython("import sys; sys.version.split()[0]"));
  log("loading numpy + pandas (one-time, cached)...");
  await pyodide.loadPackage(["numpy","pandas"]);
  log("installing arbbound source into the browser filesystem...");
  pyodide.runPython(`
import os, sys
os.makedirs('/home/pyodide/arbbound', exist_ok=True)
`);
  for (const [name, src] of Object.entries(SOURCES)) {
    pyodide.FS.writeFile("/home/pyodide/arbbound/" + name, src);
  }
  pyodide.runPython(`
import sys
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
import arbbound
from arbbound.cli import build_report, _load
from arbbound.report import render
from arbbound.ingest import basis_history
import io, time, json
`);
  log("arbbound imported in-browser: version " + pyodide.runPython("arbbound.__version__"));
  ready = true;
  setStatus("ready — provide input, then Run", "ok");
  $("btnRun").disabled = false;
}

// Expose a runner that takes the user's text and returns report JSON + rendered HTML.
async function runAnalysis(text){
  const started = performance.now();
  pyodide.globals.set("__user_input__", text);
  const resultJson = pyodide.runPython(`
import io, time, json
import pandas as pd
from arbbound.cli import build_report
from arbbound.ingest import load_csv_bhavcopy, basis_history
from arbbound.report import render

t0 = time.perf_counter()
text = __user_input__

# Write the user's text to a real file and go through the normal loader, so the
# guest path is identical to the CLI path - no special-casing for the browser.
with open('/home/pyodide/user_input.csv', 'w') as fh:
    fh.write(text)

frame = load_csv_bhavcopy('/home/pyodide/user_input.csv')
report = build_report(frame)

# Render the full dashboard from the same report, charts included.
html = render(report, basis_history(frame))

json.dumps({
    "rows": int(len(frame)),
    "traded": int((~frame["no_trade"]).sum()),
    "start": str(frame["date"].min().date()),
    "end": str(frame["date"].max().date()),
    "pairs": len(report["walk_forward"]),
    "breached": report["verdict_summary"]["pairs_ever_clearing_bound"],
    "flagged": report["verdict_summary"]["flagged_days_total"],
    "reachable": report["verdict_summary"]["flagged_days_executable"],
    "html": html,
    "elapsed": (time.perf_counter() - t0) * 1000.0,
})
`);
  const out = JSON.parse(resultJson);
  out.wall_ms = performance.now() - started;
  return out;
}

$("btnSample").onclick = async () => {
  const text = await loadSampleText();
  $("input").value = text;
  log("loaded " + SAMPLE_LABEL + " (" + text.split("\n").length + " lines)");
};
$("btnClear").onclick = () => { $("input").value = ""; };

$("file").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const text = await f.text();
  if (f.name.endsWith(".json")) {
    // MCX embeds a JSON array; accept it and convert to CSV here.
    try {
      const arr = JSON.parse(text);
      const rows = Array.isArray(arr) ? arr : (arr.data || arr.rows || []);
      if (rows.length) {
        const cols = ["Date","Symbol","ExpiryDate","Open","High","Low","Close","PreviousClose","Volume","OpenInterest","InstrumentName"];
        const hdr = cols.join(",");
        const body = rows.map(r => cols.map(c => {
          const v = r[c] !== undefined ? r[c] : (r[c.charAt(0).toLowerCase()+c.slice(1)] ?? "");
          return typeof v === "string" && v.includes(",") ? '"'+v+'"' : v;
        }).join(",")).join("\n");
        $("input").value = hdr + "\n" + body;
        log("converted JSON bhavcopy: " + rows.length + " rows");
        return;
      }
    } catch (err) { /* fall through to raw text */ }
  }
  $("input").value = text;
  log("loaded " + f.name + " (" + Math.round(text.length/1024) + " KB)");
});

$("btnRun").onclick = async () => {
  const text = $("input").value.trim();
  if (!text) { log("nothing to run - provide input first"); return; }
  $("btnRun").disabled = true;
  setStatus("running…", "idle");
  logEl.textContent = "";
  // Clear the previous result so a failed run can never leave a stale verdict
  // on screen next to an error.
  $("out").srcdoc = "";
  metaEl.textContent = "";
  log("input: " + text.split("\n").length + " lines, " + Math.round(text.length/1024) + " KB");
  try {
    const r = await runAnalysis(text);
    log("parsed " + r.rows + " rows (" + r.traded + " traded), " + r.start + " to " + r.end);
    log("tested " + r.pairs + " contract pairs in " + r.elapsed.toFixed(0) + " ms");
    log("verdict: " + r.breached + " pair(s) cleared the bound; " + r.reachable + " of " + r.flagged + " flagged days reachable");
    $("out").srcdoc = r.html;
    setStatus("done", "ok");
    metaEl.textContent = r.rows.toLocaleString() + " rows · " + r.start + " → " + r.end
      + " · computed in " + Math.round(r.elapsed) + " ms";
  } catch (err) {
    const msg = (err && err.message) ? err.message : String(err);
    // Show the human-readable reason, not a raw Python traceback.
    const friendly = /Symbol|KeyError/.test(msg)
      ? "input rejected: expected bhavcopy columns (date, symbol, close, ...) — see the header note above"
      : ("input rejected: " + msg.split("\n").filter(l => l.trim()).slice(-1)[0]);
    log(friendly);
    setStatus("input rejected", "bad");
  } finally {
    $("btnRun").disabled = false;
  }
};

boot().catch(err => {
  log("failed to boot: " + (err && err.message ? err.message : err));
  setStatus("runtime failed to load", "bad");
});
</script>
</body></html>"""