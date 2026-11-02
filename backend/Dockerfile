# syntax=docker/dockerfile:1
# Backend image: uv resolves/installs in a builder stage; the runtime stage only receives the finished
# virtualenv, so no uv, pip caches, compilers or package manager state ship in the final image.
#
#   docker build -t app-backend:local backend
#
# Migrations are a separate step, never at app start:
#   docker run --rm -e DATABASE_URL=... app-backend:local alembic upgrade head

# Every base image is pinned by tag AND digest: the tag is for humans, the digest makes builds
# reproducible and tamper-evident. Dependabot (docker ecosystem) bumps both together. Literal FROM
# lines (no ARG) so Dependabot can see them; uv is its own stage for the same reason.
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS builder
# Copying uv's static binary avoids installing it via pip/curl.
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1
WORKDIR /app

# Layer 1: third-party dependencies only. Rebuilt only when pyproject.toml or uv.lock change.
# --frozen: install exactly what uv.lock says, never re-resolve.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

# Layer 2: the application itself, installed non-editable so the venv is self-contained.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS runtime
ARG VERSION=dev
ARG REVISION=unknown
ARG CREATED=unknown
LABEL org.opencontainers.image.title="app-backend" \
      org.opencontainers.image.description="Items API (FastAPI)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${CREATED}"

# Remove pip from the runtime image. The app is installed from the builder's venv and nothing installs
# packages at runtime, but pip vendors its own copies of urllib3/msgpack/setuptools, which scanners
# flag (CVEs we cannot fix via uv.lock). Dropping pip, its ensurepip wheel and its entry points fixes
# that at the root and shrinks the attack surface (no package installer for an attacker to use).
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.13/ensurepip/_bundled \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13

# Fixed numeric uid/gid so Kubernetes `runAsNonRoot` can verify it without resolving names.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

# Read-only root FS friendly: no bytecode writes (already compiled at build), unbuffered logs,
# and nothing in the app writes to disk.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app
# Root-owned and not writable by uid 10001: the code cannot be modified at runtime.
COPY --from=builder /app/.venv /app/.venv
# alembic.ini + migrations live in WORKDIR so `alembic upgrade head` works as a command override.
COPY alembic.ini ./
COPY migrations ./migrations

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
