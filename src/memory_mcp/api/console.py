"""Console sign-in REST routes (/api/v1/console/*); see console_auth.py and docs/adr/0001.

AuthMiddleware lets these through without credentials (after the Origin check for writes);
each handler checks the session it needs.
"""
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .. import console_auth
from .routes import _json_body, err, ok


def _with_cookie(response: JSONResponse, token: str) -> JSONResponse:
    response.set_cookie(
        console_auth.COOKIE, token, max_age=console_auth.SESSION_SECONDS,
        httponly=True, secure=True, samesite="strict", path="/",
    )
    return response


def _session(request: Request):
    return getattr(request.state, "session", None)


# GET /api/v1/console/session
async def handle_session(request: Request) -> JSONResponse:
    session = _session(request)
    return ok({
        "signed_in": session is not None,
        "password_set": await console_auth.password_set(),
        "bootstrap": bool(session and session.bootstrap),
    })


# POST /api/v1/console/login  body {password} or {token} (token only while no password exists)
async def handle_login(request: Request) -> JSONResponse:
    try:
        body = await _json_body(request)
        token = await console_auth.sign_in(body.get("password") or None, body.get("token") or None)
    except console_auth.SignInError as e:
        return err(str(e), 401)
    except ValueError as e:
        return err(str(e))
    return _with_cookie(ok({"signed_in": True}), token)


# POST /api/v1/console/logout
async def handle_logout(request: Request) -> JSONResponse:
    session = _session(request)
    if session is not None:
        await console_auth.end_session(session)
    response = ok({"signed_in": False})
    response.delete_cookie(console_auth.COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return response


# PUT /api/v1/console/password  body {current_password?, new_password}
async def handle_password(request: Request) -> JSONResponse:
    session = _session(request)
    if session is None:
        return err("Unauthorized", 401)
    try:
        body = await _json_body(request)
        await console_auth.set_password(session, body.get("current_password"), str(body.get("new_password") or ""))
    except ValueError as e:
        return err(str(e))
    return ok({"password_set": True})


# DELETE /api/v1/console/sessions  — sign out everywhere
async def handle_end_all(request: Request) -> JSONResponse:
    session = _session(request)
    if session is None or session.bootstrap:
        return err("Unauthorized", 401)
    removed = await console_auth.end_all_sessions()
    response = ok({"signed_out": removed})
    response.delete_cookie(console_auth.COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return response


routes = [
    Route("/api/v1/console/session", endpoint=handle_session, methods=["GET"]),
    Route("/api/v1/console/login", endpoint=handle_login, methods=["POST"]),
    Route("/api/v1/console/logout", endpoint=handle_logout, methods=["POST"]),
    Route("/api/v1/console/password", endpoint=handle_password, methods=["PUT"]),
    Route("/api/v1/console/sessions", endpoint=handle_end_all, methods=["DELETE"]),
]
