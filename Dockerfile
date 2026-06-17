# syntax=docker/dockerfile:1
#
# medmcp-dicom — DICOM/BIDS tool stack as a fixed-environment MCP stdio server.
# CPU-only and cleanly multi-arch (all deps, incl. dcm2niix, have aarch64 wheels).
# Launched by the core via `docker run -i`; speaks JSON-RPC over stdin/stdout.
ARG BASE_IMAGE=medmcp-base:dev
FROM ${BASE_IMAGE} AS runtime

WORKDIR /app

# Frozen install from the committed lock (build-time network; runtime offline).
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

ENV PATH=/app/.venv/bin:$PATH \
    UV_NO_SYNC=1

# stdio MCP server. tini reaps the process and forwards signals; stdio passes through.
ENTRYPOINT ["tini", "--", "medmcp-dicom"]
