FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS application
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MULAN_DATA_DIR=/data \
    MULAN_RESOURCE_TTL_HOURS=24 \
    MULAN_MAX_UPLOAD_MB=512
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/dist/ ./backend/mulan/static/
RUN pip install --no-cache-dir .
RUN mkdir -p /data && chown -R 10001:10001 /app /data
USER 10001
WORKDIR /app/backend
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--access-logfile", "-", "mulan.wsgi:app"]
