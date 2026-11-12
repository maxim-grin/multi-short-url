# No uv-on-python tag exists for 0.13.2 (CI's UV_VERSION), so take the uv
# binary from its own image and run it on the same python as the runtime.
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.2 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Dependencies before source: cached until pyproject.toml or uv.lock change.
COPY app/pyproject.toml app/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

COPY app/src/ ./src/
# Non-editable: the venv alone must run, since the runtime has no source tree.
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm
# uid 10001; a PV mounted at /data is often root-owned, so the pod needs securityContext fsGroup 10001.
RUN groupadd --gid 10001 shortener \
 && useradd --uid 10001 --gid 10001 --no-create-home shortener \
 && mkdir /data && chown 10001:10001 /data
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" SHORTENER_DB_PATH=/data/links.db PORT=8080
USER 10001:10001
VOLUME /data

EXPOSE 8080
CMD ["python", "-m", "shortener"]
