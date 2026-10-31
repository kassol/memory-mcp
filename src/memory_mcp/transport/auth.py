"""Request authentication (docs/adr/0001).

A request carries either an access token (Bearer) or a console session (cookie):
- MCP accepts only access tokens.
- Administrative endpoints (settings, and later providers, tokens, restart) accept only a full
  console session; a bootstrap session may only set the password.
- Memory and finding endpoints accept either.
- State-changing requests authenticated by cookie must carry an Origin equal to the service's own.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .. import console_auth

_PUBLIC = ("/health",)
# Sign-in and session status work without credentials; their handlers check the session themselves.
_CONSOLE = "/api/v1/console/"
_ADMIN = ("/api/v1/settings",)
_SAFE = {"GET", "HEAD", "OPTIONS"}


def _deny(message: str, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def _expected_origin(request: Request) -> str:
    # Behind the reverse proxy the app sees http; the browser's Origin carries the public scheme.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("host", request.url.netloc)
    return f"{proto}://{host}"


def same_origin(request: Request) -> bool:
    return request.headers.get("origin") == _expected_origin(request)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header and header.startswith("Bearer "):
        return header.split(" ", 1)[1]
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # /ui/ serves only static files with no data.
        if path in _PUBLIC or path in ("/ui",) or path.startswith("/ui/") or request.method == "OPTIONS":
            return await call_next(request)

        bearer = _bearer(request)
        if bearer is not None:
            if not console_auth.is_config_token(bearer):
                return _deny("Forbidden", 403)
            if path.startswith(_ADMIN) or path.startswith(_CONSOLE):
                return _deny("This endpoint accepts only a console session", 403)
            request.state.credential = "access_token"
            return await call_next(request)

        if path == "/mcp":
            return _deny("Unauthorized", 401)

        session = await console_auth.session_for(request.cookies.get(console_auth.COOKIE))
        request.state.session = session
        if request.method not in _SAFE and (session is not None or path.startswith(_CONSOLE)) \
                and not same_origin(request):
            return _deny("Cross-site request rejected", 403)
        if path.startswith(_CONSOLE):
            return await call_next(request)
        if session is None:
            return _deny("Unauthorized", 401)
        if session.bootstrap:
            return _deny("Set the admin password first", 403)
        request.state.credential = "console_session"
        return await call_next(request)
