FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Create data directories
RUN mkdir -p /app/data/vectors /app/data/graph

# Expose port
EXPOSE 8765

# Start command
CMD ["python", "-m", "memory_mcp"]
