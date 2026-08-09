#!/usr/bin/env sh
set -eu

case "${PORT:-}" in
    ''|*[!0-9]*|0) echo "PORT must be a positive integer" >&2; exit 1 ;;
esac
case "${WEB_CONCURRENCY:-}" in
    ''|*[!0-9]*|0) echo "WEB_CONCURRENCY must be a positive integer" >&2; exit 1 ;;
esac
case "${GDS_REQUEST_TIMEOUT_SECONDS:-}" in
    ''|*[!0-9]*|0) echo "GDS_REQUEST_TIMEOUT_SECONDS must be a positive integer" >&2; exit 1 ;;
esac

exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --worker-class uvicorn_worker.UvicornWorker \
    --timeout "${GDS_REQUEST_TIMEOUT_SECONDS}" \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    app:app
