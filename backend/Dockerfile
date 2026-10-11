# syntax=docker/dockerfile:1
# Production Dockerfile for KintsuTech Backend
# Build from repository root:
#   docker build -f backend/Dockerfile -t kintsutech-backend:latest .

FROM python:3.12-slim AS builder

WORKDIR /build

# Install CA certificates and curl for uv installer
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# Copy package requirements from backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# Final slim production runner image
FROM python:3.12-slim AS runner

WORKDIR /app

# Create unprivileged system user and group
RUN groupadd -r kintsu && useradd -r -g kintsu -d /app -s /sbin/nologin kintsu

# Copy virtual environment from builder stage
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy backend app and AI engine
COPY backend/app /app/app
COPY ai_engine /app/ai_engine
COPY backend/pyproject.toml /app/pyproject.toml

# Set python path so both app and ai_engine packages are directly importable
ENV PYTHONPATH="/app:/app/ai_engine"

# Create persistent data directory for SQLite
RUN mkdir -p /app/data && chown -R kintsu:kintsu /app

USER kintsu

VOLUME ["/app/data"]

ENV ENVIRONMENT=production \
    PYTHONUNBUFFERED=1 \
    KINTSUTECH_DATABASE_URL="sqlite:////app/data/kintsutech.db" \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').getcode() == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
