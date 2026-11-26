# Linux image for ranked matches: bubblewrap, the compiled seccomp policy and a read-only
# virtualenv holding the engine and the harness. CI runs the adversarial suite in it.
#   docker build -f sandbox/Dockerfile -t arena-sandbox .
#   docker run --rm --privileged arena-sandbox pytest sandbox/tests

FROM debian:trixie-slim AS seccomp
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-seccomp \
    && rm -rf /var/lib/apt/lists/*
COPY sandbox/seccomp_policy.py /build/
RUN python3 /build/seccomp_policy.py /build/seccomp.bpf

FROM python:3.14-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap procps \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/arena/venv \
    UV_PYTHON=/usr/local/bin/python3.14 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY engine engine
COPY starter_kit starter_kit
COPY sandbox sandbox
COPY server server
RUN uv sync --locked --all-packages --no-editable && chmod -R a+rX /opt/arena
COPY --from=seccomp /build/seccomp.bpf /opt/arena/seccomp.bpf
ENV ARENA_VENV=/opt/arena/venv \
    ARENA_SECCOMP=/opt/arena/seccomp.bpf \
    ARENA_CGROUP_ROOT=/sys/fs/cgroup/arena-bots \
    PATH=/opt/arena/venv/bin:$PATH
ENTRYPOINT ["/app/sandbox/entrypoint.sh"]
