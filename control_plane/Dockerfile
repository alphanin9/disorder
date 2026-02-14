FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends docker.io docker-compose ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY control_plane /app/control_plane
COPY cli /app/cli
COPY images /app/images

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . && \
    chmod +x /app/control_plane/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/control_plane/entrypoint.sh"]
