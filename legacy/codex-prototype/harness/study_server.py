"""Local study server: serves learning/ pages and records quiz outcomes.

Material pages are plain files, but answering embedded quizzes needs a write
path into the learner record. This tiny stdlib server provides it:

  GET  /...            -> files under learning/ (dashboard, materials)
  POST /record         -> {"kc_hint": str, "question": str, "correct": 0|1}
                          appended to kt/data/sequences.csv via the KC store,
                          exactly like agent-graded outcomes

Everything stays on localhost; no external requests.

Usage: python3 -m harness.study_server [port]   (default 8787)
"""
from __future__ import annotations

import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness.kc_map import KCStore


class StudyHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, directory=str(root / "learning"), **kwargs)

    def log_message(self, *_):  # keep the terminal quiet
        pass

    def do_POST(self):
        if self.path.rstrip("/") != "/record":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            state = self.root / "kt" / "data"
            store = KCStore(state / "kc.json")
            q = store.assign(str(data["question"]), kc_hint=str(data["kc_hint"]))
            store.record_outcome(state / "sequences.csv", user_id="local",
                                 q=q, correct=int(data["correct"]))
            # refresh the dashboard so progress is visible on reload
            try:
                from harness.dashboard import build_dashboard
                build_dashboard(self.root)
            except Exception:
                pass
            body = json.dumps({"ok": True, "kc_id": q.kc_id, "q_id": q.q_id}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:  # noqa: BLE001
            self.send_error(400, str(e))


def serve(root: Path | str, port: int = 8787) -> ThreadingHTTPServer:
    root = Path(root)
    server = ThreadingHTTPServer(("127.0.0.1", port),
                                 partial(StudyHandler, root=root))
    return server


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    s = serve(Path.cwd(), port)
    print(f"oh-my-brain study server: http://localhost:{port}/dashboard.html "
          f"(Ctrl-C to stop)")
    s.serve_forever()
