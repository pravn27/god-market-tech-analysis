"""A local page that shows the data jobs' progress. It reads the database and never runs or changes a job.

Serves one HTML page and one JSON endpoint. The page polls the endpoint while it is open, so progress
of a run in flight updates on its own. Bind to 127.0.0.1 unless you mean to share it.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from .telemetry import status_payload

DEFAULT_PORT = 8765
POLL_MILLISECONDS = 3000


def serve(db: Path, *, host: str, port: int, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _Handler)
    server.db_path = Path(db)  # type: ignore[attr-defined]
    server.clock = clock  # type: ignore[attr-defined]
    return server


class _Handler(BaseHTTPRequestHandler):
    server: ThreadingHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - name fixed by http.server
        if self.path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif self.path == "/api/status":
            body = json.dumps(_load(self.server.db_path, self.server.clock())).encode("utf-8")  # type: ignore[attr-defined]
            self._send(200, "application/json", body)
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not found")

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - signature fixed by http.server
        return  # Keep the terminal quiet; the page polls every few seconds.


def _load(db: Path, now: datetime) -> dict:
    if not db.exists():
        return {"generated_at": now.isoformat(), "jobs": [], "message": "No database yet. No job has run."}
    conn = sqlite3.connect(db, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        return status_payload(conn, now=now)
    except sqlite3.OperationalError as error:
        return {"generated_at": now.isoformat(), "jobs": [], "message": f"The database is not ready: {error}"}
    finally:
        conn.close()


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data jobs</title>
<style>
  body { font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2328; background: #f6f8fa; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .muted { color: #6e7781; }
  .card { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; margin: 16px 0; }
  .card h2 { font-size: 16px; margin: 0 0 8px; }
  .chips span { display: inline-block; padding: 2px 8px; margin-right: 6px; border-radius: 12px; background: #eaeef2; font-size: 12px; }
  .chips .succeeded { background: #dafbe1; color: #116329; }
  .chips .partial, .chips .stalled { background: #fff8c5; color: #7d4e00; }
  .chips .failed { background: #ffebe9; color: #82071e; }
  .chips .running { background: #ddf4ff; color: #0969da; }
  .chips .overdue { background: #ffebe9; color: #82071e; font-weight: 600; }
  .bar { height: 10px; background: #eaeef2; border-radius: 6px; overflow: hidden; margin: 8px 0; }
  .bar div { height: 100%; background: #2da44e; }
  .bar .bad { background: #cf222e; }
  table { border-collapse: collapse; width: 100%; margin-top: 8px; }
  th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #eaeef2; font-size: 13px; }
  th { color: #6e7781; font-weight: 600; }
  .error { color: #82071e; font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  details { margin-top: 8px; }
  summary { cursor: pointer; color: #0969da; }
</style>
</head>
<body>
<h1>Data jobs</h1>
<div class="muted" id="meta">Loading...</div>
<div id="jobs"></div>
<script>
(function () {
  "use strict";

  function el(tag, text, className) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    if (className) { node.className = className; }
    return node;
  }

  function when(value) {
    if (!value) { return "never"; }
    var date = new Date(value);
    return isNaN(date.getTime()) ? value : date.toLocaleString();
  }

  function chip(text, className) { return el("span", text, className); }

  function table(headers, rows) {
    var t = el("table");
    var head = el("tr");
    headers.forEach(function (h) { head.appendChild(el("th", h)); });
    t.appendChild(head);
    rows.forEach(function (cells) {
      var tr = el("tr");
      cells.forEach(function (cell) {
        var td = el("td");
        if (cell instanceof Node) { td.appendChild(cell); } else { td.textContent = cell === null || cell === undefined ? "" : String(cell); }
        tr.appendChild(td);
      });
      t.appendChild(tr);
    });
    return t;
  }

  function progressBar(progress) {
    var wrap = el("div", null, "bar");
    var done = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
    var fill = el("div");
    fill.style.width = done + "%";
    if (progress.failed > 0) { fill.className = "bad"; }
    wrap.appendChild(fill);
    return wrap;
  }

  function jobCard(job) {
    var card = el("section", null, "card");
    card.appendChild(el("h2", job.name));

    var chips = el("div", null, "chips");
    if (job.latest_status) { chips.appendChild(chip("latest run " + job.latest_status, job.latest_status)); }
    if (job.overdue) { chips.appendChild(chip("overdue", "overdue")); }
    chips.appendChild(chip("every " + Math.round(job.interval_seconds / 3600) + " h"));
    card.appendChild(chips);

    var facts = el("div", null, "muted");
    facts.textContent = "Next run: " + when(job.next_run_at) + "  |  Last fully successful run: " + when(job.last_full_success_at);
    card.appendChild(facts);

    if (job.progress) {
      var p = job.progress;
      card.appendChild(progressBar(p));
      card.appendChild(el("div", p.done + " of " + p.total + " done, " + p.failed + " failed in the latest run"));
    } else {
      card.appendChild(el("div", "No run yet.", "muted"));
    }

    if (job.coverage.length) {
      var cov = el("div", null, "chips");
      job.coverage.forEach(function (c) { cov.appendChild(chip(c.period + " " + c.status, c.status)); });
      card.appendChild(el("div", "Recent periods, newest first:", "muted"));
      card.appendChild(cov);
    }

    var failed = job.items.filter(function (item) { return item.status === "failed"; });
    if (failed.length) {
      var details = el("details");
      details.appendChild(el("summary", "Failed items (" + failed.length + ")"));
      details.appendChild(table(["Symbol", "Timeframe", "Error"], failed.map(function (item) {
        return [item.symbol, item.timeframe, el("span", item.error || "", "error")];
      })));
      card.appendChild(details);
    }

    if (job.items.length) {
      var all = el("details");
      all.appendChild(el("summary", "All items in the latest run (" + job.items.length + ")"));
      all.appendChild(table(["Symbol", "Timeframe", "Status", "Fetched"], job.items.map(function (item) {
        return [item.symbol, item.timeframe, item.status, when(item.fetched_at)];
      })));
      card.appendChild(all);
    }

    if (job.runs.length) {
      card.appendChild(el("div", "Recent runs", "muted"));
      card.appendChild(table(["Run", "Period", "Status", "Started", "Finished", "Items", "Bars new / changed / same"], job.runs.map(function (run) {
        return [
          "#" + run.id, run.period_key, run.status, when(run.started_at), when(run.finished_at),
          run.items_total,
          run.bars_inserted + " / " + run.bars_updated + " / " + run.bars_unchanged
        ];
      })));
    }
    return card;
  }

  function render(payload) {
    var jobs = document.getElementById("jobs");
    jobs.replaceChildren();
    document.getElementById("meta").textContent =
      "Updated " + new Date().toLocaleTimeString() + ". Refreshes every " + (POLL / 1000) + " seconds.";
    if (payload.message) { jobs.appendChild(el("div", payload.message, "card")); }
    payload.jobs.forEach(function (job) { jobs.appendChild(jobCard(job)); });
  }

  var POLL = __POLL__;
  function poll() {
    fetch("/api/status", { cache: "no-store" })
      .then(function (r) { if (!r.ok) { throw new Error("HTTP " + r.status); } return r.json(); })
      .then(render)
      .catch(function (error) {
        document.getElementById("meta").textContent = "Cannot reach the server: " + error.message;
      });
  }
  poll();
  setInterval(poll, POLL);
})();
</script>
</body>
</html>
""".replace("__POLL__", str(POLL_MILLISECONDS))
