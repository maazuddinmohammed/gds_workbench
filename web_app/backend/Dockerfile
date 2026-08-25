FROM python:3.14.7-slim-trixie@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /workspace

RUN python -m pip install --no-cache-dir uv==0.11.14
COPY mcp_server/ /workspace/mcp_server/
COPY web_app/backend/ /workspace/web_app/backend/
RUN cd /workspace/web_app/backend && \
    uv sync --frozen --no-dev --no-editable


FROM python:3.14.7-slim-trixie@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime

ENV HOME=/tmp \
    PATH=/workspace/web_app/backend/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp
WORKDIR /app

RUN groupadd --gid 10001 gds && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin gds
COPY --from=build --chown=10001:10001 \
    /workspace/web_app/backend/.venv /workspace/web_app/backend/.venv

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)"]
CMD ["uvicorn", "gds_workbench_api.runtime:create_runtime_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
