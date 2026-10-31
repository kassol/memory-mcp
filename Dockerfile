# Console build (web/): its output goes into the Python package's ui/ directory.
# The runtime image below has no Node.
FROM node:24-slim AS console
WORKDIR /build/web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install locked Python dependencies
COPY requirements.lock pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src/ src/
COPY --from=console /build/src/memory_mcp/ui src/memory_mcp/ui
COPY alembic.ini ./alembic.ini
RUN pip install --no-cache-dir --no-deps .

# Create data directories
RUN mkdir -p /app/data/vectors

# Expose port
EXPOSE 8765

# jieba lazy-loads its dictionary on first call; nothing to pre-warm.
# Alembic upgrade head runs at FastAPI lifespan startup (auto_migrate=true).

CMD ["python", "-m", "memory_mcp"]
