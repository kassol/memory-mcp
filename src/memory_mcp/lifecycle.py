"""Applying startup settings restarts the process (issue #14, docs/adr/0002).

`apply` writes the checked settings, then asks for a restart: the process stops accepting requests,
waits for a maintenance round in progress (up to 30 seconds), lets uvicorn drain the requests still
in flight, and exits with `EXIT_CODE`. The restart policy starts it again; the marker in
`startup-apply.json` tells the next start whether that was a fresh apply (and whether it came up).
"""
import asyncio
import contextlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

EXIT_CODE = 88
DRAIN_TIMEOUT = 30.0
RESPONSE_GRACE = 0.2  # seconds to let the apply response leave before the socket closes

_server = None
_task: Optional[asyncio.Task] = None
_requested = False


def bind(server) -> None:
    """Give the lifecycle the uvicorn server, so it can stop accepting requests."""
    global _server
    _server = server


def restart_requested() -> bool:
    return _requested


def exit_code() -> int:
    return EXIT_CODE if _requested else 0


async def _drain() -> None:
    logger.info("restart requested: draining before exit")
    # A maintenance round must not be cut in half: wait for it while requests are still served, then
    # stop accepting, and let uvicorn finish what is in flight before the process exits.
    from .engine import maintenance

    await asyncio.sleep(RESPONSE_GRACE)
    try:
        await maintenance.wait_idle(DRAIN_TIMEOUT)
    except Exception:  # a broken round must not keep the process up
        logger.warning("waiting for the maintenance round failed", exc_info=True)
    if _server is not None:
        logger.info("asking uvicorn to stop accepting requests")
        _server.should_exit = True
    else:
        logger.warning("no uvicorn server bound; the process will not exit")


def request_restart() -> None:
    """Schedule the restart; the caller has already written the new settings."""
    global _task, _requested
    _requested = True
    if _task is None or _task.done():
        _task = asyncio.create_task(_drain())


async def settle() -> None:
    """Where the process waits before exiting: the drain is bounded, so this always returns."""
    if _task is not None:
        with contextlib.suppress(Exception):
            await _task


def reset_for_tests() -> None:
    global _server, _task, _requested
    _server, _task, _requested = None, None, False
