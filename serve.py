#!/usr/bin/env python3
"""Local server for the Nimble Rubric Evaluator.

Serves index.html and forwards /ollama/* to your local Ollama, so the browser
never has to deal with CORS. Cloud providers (TypeSafe Jev, OpenAI, Anthropic,
Gemini, OpenRouter, Groq...) go through /remote/*, which only forwards to the
HTTPS hosts listed in ALLOWED_HOSTS (add more with EXTRA_HOSTS=host1,host2).
Python 3.8+, standard library only.

    python3 serve.py                 # http://localhost:8787
    python3 serve.py --port 9000
    OLLAMA_HOST=http://192.168.1.20:11434 python3 serve.py
"""
import argparse
import urllib.parse
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

ALLOWED_HOSTS = {
    "api.typesafe.ai",                      # TypeSafe Jev (cloud decision API)
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",    # Google Gemini (OpenAI-compatible endpoint)
    "openrouter.ai",
    "api.groq.com",
    "api.together.xyz",
    "api.mistral.ai",
    "api.deepseek.com",
}
ALLOWED_HOSTS |= {h.strip().lower() for h in os.environ.get("EXTRA_HOSTS", "").split(",") if h.strip()}
FORWARD_HEADERS = ("Authorization", "x-api-key", "anthropic-version", "api-key")


def host_allowed(host):
    host = (host or "").lower()
    return host in ALLOWED_HOSTS or host.endswith(".openai.azure.com")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def log_message(self, fmt, *args):
        if (self.path or "").startswith(("/ollama/", "/remote/")):
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    def _send_json(self, status, text):
        data = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self):
        remote = self.path.startswith("/remote/")
        if remote:
            # The browser names the upstream base URL in X-Upstream, e.g. https://api.typesafe.ai/v1
            base = (self.headers.get("X-Upstream") or "").rstrip("/")
            u = urllib.parse.urlparse(base)
            if u.scheme != "https" or not host_allowed(u.hostname):
                return self._send_json(403, '{"error": "serve.py only forwards to known HTTPS AI providers. '
                                       'Host %s is not allowed; add it with EXTRA_HOSTS=%s"}'
                                       % (u.hostname or base, u.hostname or "host"))
            target = base + self.path[len("/remote"):]
            upstream = u.hostname
        else:
            target = OLLAMA + self.path[len("/ollama"):]
            upstream = OLLAMA
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(target, data=body, method=self.command)
        req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
        if remote:
            req.add_header("User-Agent", "nimble-rubric-evaluator")
            for h in FORWARD_HEADERS:
                if self.headers.get(h):
                    req.add_header(h, self.headers.get(h))
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                status, data, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, data, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
        except Exception as e:  # Ollama not running, refused, timeout, no internet
            status, ctype = 502, "application/json"
            hint = "Check your internet connection" if remote else "Is it running? Try: ollama serve"
            data = ('{"error": "Could not reach %s (%s). %s"}'
                    % (upstream, str(e).replace('"', "'").replace("\\", "/"), hint)).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith(("/ollama/", "/remote/")):
            return self._proxy()
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith(("/ollama/", "/remote/")):
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
