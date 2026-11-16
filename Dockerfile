FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CLAUDE.md corre pytest y ruff dentro de `web`: por eso la imagen incluye el extra dev.
COPY pyproject.toml ./
RUN pip install ".[dev]"

COPY . .

RUN useradd --system --create-home app \
    && mkdir -p /app/staticfiles \
    && chown -R app:app /app
USER app

EXPOSE 8000
