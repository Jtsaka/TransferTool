# Compass — Cloud Run image.
#
# Cloud Run expects the container to listen on $PORT (default 8080).
# The backend reads $PORT in backend/config.py.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install Python deps first so layer caching works.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project (backend, static HTML/CSS/JS, assets).
COPY . .

# Drop privileges.
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8080

# 2 workers x 4 threads is a sensible default for I/O-bound Gemini calls on
# the smallest Cloud Run instance. Tune via env if needed.
CMD exec gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers ${WEB_CONCURRENCY:-2} \
    --threads ${GUNICORN_THREADS:-4} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    backend.app:app
