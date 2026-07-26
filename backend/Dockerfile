# syntax=docker/dockerfile:1

# =============================================================================
# Backend image
#
# Single stage: there is nothing to compile, and every wheel installed here is
# needed at runtime, so a builder stage would add complexity without shrinking
# the result.
# =============================================================================
FROM python:3.13-slim

# PYTHONDONTWRITEBYTECODE  - .pyc files are dead weight in an immutable image
# PYTHONUNBUFFERED         - without it, logs sit in a buffer and `docker logs`
#                            shows nothing until the process exits
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies are copied and installed before the application code so that
# editing a source file does not invalidate the (slow) install layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as an unprivileged user. A container process running as root that is
# compromised is running as root on the host kernel.
#
# /data holds the SQLite file and is a mount point for a named volume, so it
# must be owned by the runtime user before the volume is attached.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

# Default to the mounted volume. Overridden by DATABASE_URL in the environment
# when pointing at PostgreSQL or MySQL.
ENV DATABASE_URL=sqlite:////data/stock_research.db

EXPOSE 8000

# Uses the stdlib rather than curl, which keeps the image free of an extra
# package whose only purpose is this check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# No --reload: it watches the filesystem and restarts on change, which is
# pointless and wasteful against read-only image layers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
