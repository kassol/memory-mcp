from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request

from ..config import settings


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # /ui/ serves only static files with no data; every data request from the page carries the token.
        path = request.url.path
        if path in ("/health", "/ui") or path.startswith("/ui/") or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

        token = auth_header.split(" ", 1)[1]
        if token != settings.auth_token:
            return JSONResponse({"ok": False, "error": "Forbidden"}, status_code=403)

        return await call_next(request)
