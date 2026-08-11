#!/usr/bin/env sh
set -eu

gds_server_port="${SERVER_PORT:-8000}"
gds_web_concurrency=2
gds_request_timeout_seconds=120

case "${gds_server_port}" in
    ''|*[!0-9]*|0) echo "SERVER_PORT must be a positive integer" >&2; exit 1 ;;
esac

exec gunicorn \
    --bind "0.0.0.0:${gds_server_port}" \
    --workers "${gds_web_concurrency}" \
    --worker-class uvicorn_worker.UvicornWorker \
    --timeout "${gds_request_timeout_seconds}" \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    app:app
