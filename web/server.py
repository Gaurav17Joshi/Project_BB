"""Browser chat UI over the saved abstraction.

  python web/server.py [--port 8000] [--open]          (uses the gpt-6-luna backend and outputs/closed)

Serves web/index.html and a small JSON API:
  GET  /api/overview        patient summaries from the abstraction (no LLM, no key needed)
  GET  /api/doc?id=BH-D103  source document text
  POST /api/ask             {"question": "..."} -> same result as `cli.py ask`
"""
import argparse
import json
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import os  # noqa: E402

# The chat always uses the closed model (outputs/closed). The local model is kept for comparison only.
os.environ["BACKBONE_BACKEND"] = "openai"
from backbone import ask, config, db, queries  # noqa: E402

INDEX = Path(__file__).resolve().parent / "index.html"
_ask_lock = threading.Lock()  # one question at a time; the DB and the model loop are not shared safely


def overview() -> dict:
    con = db.connect()
    try:
        patients = []
        for p in queries.list_patients(con):
            mrn = p["mrn"]
            goals = queries.treatment_goals(con, mrn)["goals"]
            counts = queries.session_counts(con, mrn)
            weeks = queries.weekly_summary(con, mrn)
            patients.append({
                **p,
                "goal": {"min_days": goals[0]["min_days"], "min_minutes": goals[0]["min_minutes"],
                         "doc_id": goals[0]["doc_id"]} if goals else None,
                "period": counts["period"],
                "sessions": {"by_type": counts["by_type"], "total": counts["total_established"],
                             "total_possible": counts["total_possible"],
                             "days": counts["distinct_therapy_days_established"]},
                "minutes": {"lo": weeks["total_minutes_lo"], "hi": weeks["total_minutes_hi"]},
                "weeks": [{k: w.get(k) for k in ("week", "therapy_days", "minutes", "verdict", "why")}
                          for w in queries.goal_compliance(con, mrn)["weeks"]],
                "measures": [{k: m.get(k) for k in ("instrument", "completed_date", "total_score")}
                             for m in queries.measures(con, mrn)["distinct_administrations"]],
                "issues": [{k: i[k] for k in ("severity", "kind", "description")}
                           for i in queries.issues(con, mrn)["issues"] if i["severity"] in ("high", "medium")],
            })
        docs = db.rows(con, "SELECT doc_id, filename, title FROM documents ORDER BY doc_id")
        qfile = config.DATA_DIR / "questions.json"
        examples = [q["question"] for q in json.loads(qfile.read_text(encoding="utf-8"))] if qfile.exists() else []
        examples += ["What happened on January 27, and why wasn't it counted?",
                     "Which weeks met the treatment-plan goal?"]
        return {"patients": patients, "documents": docs, "examples": examples, "model": config.ANSWER_MODEL}
    finally:
        con.close()


def document(doc_id: str) -> dict | None:
    con = db.connect()
    try:
        r = db.rows(con, "SELECT doc_id, filename, title, text FROM documents WHERE doc_id=? OR filename=?", (doc_id, doc_id))
        return r[0] if r else None
    finally:
        con.close()


def answer(question: str) -> dict:
    with _ask_lock:
        con = db.connect()
        try:
            r = ask.answer(con, question, save_dir=config.OUT_DIR / "answers" / "web")
        finally:
            con.close()
    keep = ("question", "answer", "tool_calls", "latency_s", "citations", "llm_calls", "input_tokens",
            "output_tokens", "cost_usd", "model")
    return {k: r.get(k) for k in keep}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path in ("/", "/index.html"):
                self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/api/overview":
                self._send(200, overview())
            elif u.path == "/api/doc":
                d = document((parse_qs(u.query).get("id") or [""])[0])
                self._send(200, d) if d else self._send(404, {"error": "unknown document"})
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/ask":
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            q = (body.get("question") or "").strip()
            if not q:
                return self._send(400, {"error": "empty question"})
            if len(q) > 2000:
                return self._send(400, {"error": "question too long (2000 characters max)"})
            print(f"ask: {q[:80]}")
            self._send(200, answer(q))
        except RuntimeError as e:  # e.g. missing API key
            self._send(503, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):  # keep the console quiet except for questions and errors
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="open the browser")
    a = ap.parse_args()
    url = f"http://{a.host}:{a.port}/"
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"Clinical review chat on {url}  (Ctrl+C to stop)")
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
