#!/usr/bin/env python3
"""Serve the SmbOS dashboard in live mode.

Usage: serve_dashboard.py [sop_dir]

GET  /?t=<token>    the dashboard, regenerated from disk on every load
POST /api/suggest   {"path": "...", "text": "..."} with X-Token header;
                    appends the suggestion to that SOP's
                    "Notes for next revision" section

Suggestions are append-only and tagged "via dashboard"; restructuring an SOP
stays with Claude's propose/approve flow. Binds 127.0.0.1 only, random port,
per-run token. Stdlib only, no network beyond localhost. Ctrl-C to stop.
"""
import json
import secrets
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_dashboard import SKIP_NAMES, build_html, resolve_sop_dir

TOKEN = secrets.token_urlsafe(16)
MAX_TEXT = 2000
NOTES_HEADING = "## Notes for next revision"


def append_suggestion(sop_dir, rel_path, text):
    root = sop_dir.resolve()
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise PermissionError("path escapes the SOP directory")
    if target.suffix != ".md" or target.name in SKIP_NAMES or not target.is_file():
        raise FileNotFoundError("not an SOP file")

    bullet = "- ({}, via dashboard) {}".format(date.today().isoformat(), " ".join(text.split()))
    content = target.read_text(encoding="utf-8")
    if NOTES_HEADING in content:
        head, _, tail = content.partition(NOTES_HEADING)
        nxt = tail.find("\n## ")
        if nxt == -1:
            content = head + NOTES_HEADING + tail.rstrip() + "\n" + bullet + "\n"
        else:
            section, rest = tail[:nxt], tail[nxt:]
            content = head + NOTES_HEADING + section.rstrip() + "\n" + bullet + "\n" + rest
    else:
        block = "\n" + NOTES_HEADING + "\n\n" + bullet + "\n"
        cl = content.find("\n## Changelog")
        if cl == -1:
            content = content.rstrip() + "\n" + block
        else:
            content = content[:cl] + block + content[cl:]
    target.write_text(content, encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    sop_dir = None

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path not in ("/", "/index.html"):
            return self._send(404, '{"error":"not found"}')
        if parse_qs(u.query).get("t", [""])[0] != TOKEN:
            return self._send(403, '{"error":"bad or missing token"}')
        html = build_html(self.sop_dir, {"live": True, "token": TOKEN})
        return self._send(200, html, "text/html")

    def do_POST(self):
        if self.path != "/api/suggest":
            return self._send(404, '{"error":"not found"}')
        if self.headers.get("X-Token") != TOKEN:
            return self._send(403, '{"error":"bad or missing token"}')
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 65536)
            payload = json.loads(self.rfile.read(length) or b"{}")
            text = str(payload.get("text", "")).strip()[:MAX_TEXT]
            if not text:
                return self._send(400, '{"error":"empty suggestion"}')
            append_suggestion(self.sop_dir, str(payload.get("path", "")), text)
            return self._send(200, '{"ok":true}')
        except (PermissionError, FileNotFoundError) as e:
            return self._send(400, json.dumps({"error": str(e)}))
        except json.JSONDecodeError:
            return self._send(400, '{"error":"invalid JSON"}')
        except Exception:
            return self._send(500, '{"error":"server error"}')


def main():
    sop_dir = resolve_sop_dir()
    Handler.sop_dir = sop_dir
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    print("SmbOS live dashboard: http://127.0.0.1:{}/?t={}".format(port, TOKEN), flush=True)
    print("Reading {}. Saved suggestions land in each SOP's notes. Ctrl-C to stop.".format(sop_dir), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
