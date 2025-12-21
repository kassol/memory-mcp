import contextlib
from typing import AsyncIterator

from mcp.server.lowlevel.server import Server as MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings


class StreamableHttpApp:

    def __init__(
        self,
        server: MCPServer,
        *,
        json_response: bool = False,
        stateless: bool = False,
        security_settings: TransportSecuritySettings | None = None,
    ) -> None:
        self._manager = StreamableHTTPSessionManager(
            server,
            json_response=json_response,
            stateless=stateless,
            security_settings=security_settings,
        )

    @contextlib.asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        async with self._manager.run():
            yield

    async def __call__(self, scope, receive, send) -> None:
        await self._manager.handle_request(scope, receive, send)
