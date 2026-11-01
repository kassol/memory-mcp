import sys

import uvicorn

from . import lifecycle
from .config import settings


def main() -> int:
    """Run the service.

    The uvicorn server is created here so the console's apply can stop accepting requests and let
    the process exit with `lifecycle.EXIT_CODE`; the restart policy starts it again. `debug` only
    raises the log level: reload spawns a supervisor process, which would swallow that exit.
    """
    config = uvicorn.Config(
        "memory_mcp.server:app",
        host=settings.host,
        port=settings.port,
        log_level="debug" if settings.debug else "info",
    )
    server = uvicorn.Server(config)
    lifecycle.bind(server)
    server.run()
    return lifecycle.exit_code()


if __name__ == "__main__":
    sys.exit(main())
