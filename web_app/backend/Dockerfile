FROM node:22.16.0-bookworm-slim@sha256:048ed02c5fd52e86fda6fbd2f6a76cf0d4492fd6c6fee9e2c463ed5108da0e34 AS frontend-build

WORKDIR /workspace
COPY package.json package-lock.json ./
COPY web_app/frontend/package.json /workspace/web_app/frontend/package.json
RUN npm ci --omit=dev
COPY web_app/frontend/ /workspace/web_app/frontend/
RUN npm run build


FROM python:3.14.7-slim-trixie@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS python-build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /workspace

RUN python -m pip install --no-cache-dir uv==0.11.14
COPY pyproject.toml uv.lock /workspace/
COPY mcp_server/ /workspace/mcp_server/
COPY web_app/backend/ /workspace/web_app/backend/
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.14.7-slim-trixie@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4 AS runtime

ENV HOME=/tmp \
    PATH=/workspace/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp
WORKDIR /app

RUN groupadd --gid 10001 gds && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin gds
COPY --from=python-build --chown=10001:10001 /workspace/.venv /workspace/.venv
COPY --from=frontend-build --chown=10001:10001 \
    /workspace/web_app/frontend/dist /app/web_app/frontend/dist

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)"]
CMD ["python", "-m", "gds_workbench_api.app_process"]
