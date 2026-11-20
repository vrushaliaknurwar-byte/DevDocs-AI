FROM python:3.11-slim

# Install system dependencies including git for repo cloning and build tools for native packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default port
ENV PORT=8000

# Expose port (Render automatically sets PORT at runtime)
EXPOSE 8000

# Health check using PORT environment variable
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run API server without --reload and bind to 0.0.0.0 on the port from PORT
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
