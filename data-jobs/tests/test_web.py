import json
import threading
import urllib.error
import urllib.request
from datetime import timedelta

from data_jobs.runner import JobSpec, run_job
from data_jobs.store import connect
from data_jobs.web import PAGE, serve
from support import NOW, FakeFetcher, FixedClock

SPEC = JobSpec(name="gm-daily", interval=timedelta(days=1), symbols=("A", "B"), timeframes=("1D",), bar_count=2)


def _serve(db):
    server = serve(db, host="127.0.0.1", port=0, clock=lambda: NOW)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.headers.get("Content-Type"), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type"), error.read()


def test_the_page_and_the_json_are_served_and_the_json_reflects_the_database(tmp_path):
    db = tmp_path / "jobs.sqlite3"
    conn = connect(db)
    run_job(conn, SPEC, FakeFetcher(), clock=FixedClock(NOW))
    conn.close()
    server, base = _serve(db)
    try:
        status, content_type, body = _get(base + "/")
        assert status == 200 and content_type.startswith("text/html")
        assert body.decode("utf-8") == PAGE

        status, content_type, body = _get(base + "/api/status")
        assert status == 200 and content_type == "application/json"
        (job,) = json.loads(body)["jobs"]
        assert job["name"] == "gm-daily"
        assert job["progress"] == {"total": 2, "done": 2, "failed": 0}
    finally:
        server.shutdown()
        server.server_close()


def test_a_missing_database_says_no_job_has_run(tmp_path):
    server, base = _serve(tmp_path / "missing.sqlite3")
    try:
        status, _, body = _get(base + "/api/status")
        payload = json.loads(body)
        assert status == 200
        assert payload["jobs"] == []
        assert payload["message"] == "No database yet. No job has run."
    finally:
        server.shutdown()
        server.server_close()


def test_unknown_paths_are_not_found(tmp_path):
    server, base = _serve(tmp_path / "jobs.sqlite3")
    try:
        status, _, _ = _get(base + "/nope")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
