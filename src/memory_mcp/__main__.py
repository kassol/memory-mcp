import uvicorn
from .config import settings

def main():
    uvicorn.run(
        "memory_mcp.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

if __name__ == "__main__":
    main()
