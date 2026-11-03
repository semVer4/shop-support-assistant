"""Local prototype. Python 3.10+, standard library only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json
from assistant import answer_question, KB, system_prompt
from llm import configured_model

ROOT = Path(__file__).resolve().parent
MODEL = configured_model()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8")

    def send_bytes(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "mode": "llm-configured" if MODEL else "model-unavailable", "version": KB["version"]})
        if path == "/api/policy":
            return self.send_json(200, {"knowledge_base": KB, "system_prompt": system_prompt()})
        files = {
            "/": ("web/index.html", "text/html; charset=utf-8"),
            "/app.js": ("web/app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("web/style.css", "text/css; charset=utf-8"),
            "/knowledge_base.json": ("knowledge_base.json", "application/json; charset=utf-8"),
            "/system_prompt.txt": ("system_prompt.txt", "text/plain; charset=utf-8"),
        }
        if path not in files:
            return self.send_json(404, {"error": "Страница не найдена"})
        name, kind = files[path]
        return self.send_bytes(200, (ROOT / name).read_bytes(), kind)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/chat":
            return self.send_json(404, {"error": "Метод не найден"})
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self.send_json(403, {"error": "Недопустимый источник запроса"})
        if self.headers.get_content_type() != "application/json":
            return self.send_json(415, {"error": "Ожидается application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 12000:
                return self.send_json(413, {"error": "Недопустимый размер запроса"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or set(data) != {"message"}:
                raise ValueError("Ожидается объект с полем message")
            reply = answer_question(data["message"], MODEL)
        except (ValueError, UnicodeDecodeError) as error:
            return self.send_json(400, {"error": str(error)})
        return self.send_json(200, reply.as_dict())

    def log_message(self, format, *args):
        # Do not log questions or credentials.
        print(f"HTTP {args[1] if len(args) > 1 else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8087)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Open http://127.0.0.1:{args.port} | mode={'llm+policy' if MODEL else 'model-unavailable'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

