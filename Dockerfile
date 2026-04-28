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
RUN pip install --no-cache-dir --no-deps .

# Create data directories
RUN mkdir -p /app/data/vectors /app/data/graph

# Expose port
EXPOSE 8765

# Start command
CMD ["python", "-m", "memory_mcp"]
