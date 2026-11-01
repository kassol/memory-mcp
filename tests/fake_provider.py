"""A local HTTP server standing in for a model provider, for tests that need to see the wire.

One path prefix per protocol (openai, anthropic, gemini), plus two knobs:
- /fail/... answers 401 with a body, to exercise error mapping;
- /badjson/... answers 200 without the expected fields;
- `reply` is the chat text the server returns.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.delay = 0.0
        self.reply = "pong"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep pytest output clean
                pass

            def do_GET(self) -> None:
                outer._handle(self)

            def do_POST(self) -> None:
                outer._handle(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeProvider":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def paths(self) -> list[str]:
        return [call["path"] for call in self.calls]

    def models_called(self) -> list[str]:
        return [call["body"]["model"] for call in self.calls if call["body"] and "model" in call["body"]]

    def _handle(self, request) -> None:
        length = int(request.headers.get("content-length") or 0)
        raw = request.rfile.read(length) if length else b""
        body = json.loads(raw) if raw else None
        self.calls.append(
            {
                "method": request.command,
                "path": request.path,
                "headers": {k.lower(): v for k, v in request.headers.items()},
                "body": body,
            }
        )
        if self.delay:
            time.sleep(self.delay)
        status, payload = self._respond(request.path.split("?", 1)[0])
        data = json.dumps(payload).encode()
        request.send_response(status)
        request.send_header("content-type", "application/json")
        request.send_header("content-length", str(len(data)))
        request.end_headers()
        request.wfile.write(data)

    def _respond(self, path: str) -> tuple[int, dict]:
        if "/fail/" in path:
            return 401, {"error": {"message": "invalid api key"}}
        if "/badjson/" in path:
            return 200, {"unexpected": True}
        protocol = path.split("/")[1]
        if protocol == "openai":
            if path.endswith("/chat/completions"):
                return 200, {"choices": [{"message": {"content": f" {self.reply} "}}]}
            if path.endswith("/embeddings"):
                return 200, {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
            if path.endswith("/models"):
                return 200, {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4.1"}]}
        if protocol == "anthropic":
            if path.endswith("/messages"):
                return 200, {"content": [{"type": "text", "text": self.reply}]}
            if path.endswith("/models"):
                return 200, {"data": [{"id": "claude-3-5-haiku"}]}
        if protocol == "gemini":
            if ":generateContent" in path:
                return 200, {"candidates": [{"content": {"parts": [{"text": self.reply}]}}]}
            if ":embedContent" in path:
                return 200, {"embedding": {"values": [0.1, 0.2, 0.3]}}
            if path.endswith("/models"):
                return 200, {"models": [{"name": "models/gemini-2.5-flash"}]}
        return 404, {"error": {"message": f"no fake route for {path}"}}


def free_port() -> int:
    """A port nothing listens on, for connection-failure tests."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
