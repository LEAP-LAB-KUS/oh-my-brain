"""Study server: serves learning/ and records quiz outcomes into the KT store."""
import json
import threading
import urllib.request
from pathlib import Path

from harness.study_server import serve


def _post(port, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/record",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_record_endpoint_appends_outcome(tmp_path: Path):
    (tmp_path / "learning").mkdir()
    (tmp_path / "learning" / "index.html").write_text("<html>ok</html>")
    server = serve(tmp_path, port=0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        out = _post(port, {"kc_hint": "js-event-loop",
                           "question": "What runs before setTimeout callbacks?",
                           "correct": 1})
        assert out["ok"] and out["kc_id"] >= 1
        rows = (tmp_path / "kt" / "data" / "sequences.csv").read_text().splitlines()
        assert rows[0].startswith("user_id") and rows[1].startswith("local,")
        # files still served
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as r:
            assert b"ok" in r.read()
    finally:
        server.shutdown()
