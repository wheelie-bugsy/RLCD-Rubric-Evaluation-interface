#!/usr/bin/env python3
"""Local server for the Nimble Rubric Evaluator.

Serves index.html and forwards /ollama/* to your local Ollama, so the browser
never has to deal with CORS. Python 3.8+, standard library only.

    python3 serve.py                 # http://localhost:8787
    python3 serve.py --port 9000
    OLLAMA_HOST=http://192.168.1.20:11434 python3 serve.py
"""
import argparse
import http.server
import os
import sys
import urllib.error
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def log_message(self, fmt, *args):
        if "/ollama/" in (self.path or ""):
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    def _proxy(self):
        target = OLLAMA + self.path[len("/ollama"):]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(target, data=body, method=self.command)
        req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                status, data, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, data, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
        except Exception as e:  # Ollama not running, refused, timeout
            status, ctype = 502, "application/json"
            data = ('{"error": "Could not reach Ollama at %s (%s). Is it running? Try: ollama serve"}'
                    % (OLLAMA, str(e).replace('"', "'"))).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/ollama/"):
            return self._proxy()
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/ollama/"):
            return self._proxy()
        self.send_error(404)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to share on your network")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    srv = http.server.ThreadingHTTPServer((a.host, a.port), Handler)
    url = "http://localhost:%d" % a.port
    print("Nimble Rubric Evaluator running at %s  (Ollama: %s)\nCtrl+C to stop." % (url, OLLAMA))
    if not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
