import importlib

import anyio


def test_starlette_lifespan_accepts_app_arg(test_env):
    async def run():
        import memory_mcp.server as server

        importlib.reload(server)

        async with server.app.router.lifespan_context(server.app):
            pass

    anyio.run(run)
