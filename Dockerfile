FROM ghcr.io/astral-sh/uv:0.10.8 AS uv

FROM python:3.12-slim AS service
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
    ASSISTANT_WORKSPACE_ROOT=/app/examples ASSISTANT_RUNS_DIR=/app/runs
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --extra test-runner --no-install-project
COPY src ./src
COPY examples ./examples
COPY benchmarks ./benchmarks
RUN uv sync --locked --no-dev --extra test-runner && \
    useradd --uid 10001 --create-home assistant && \
    mkdir /app/runs && chown assistant:assistant /app/runs
USER assistant
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "code_assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]

# Host CLI sandbox for trusted test suites with dependencies already baked into the image.
# Historical SWE-bench evaluation uses the upstream per-instance images instead.
FROM python:3.12-slim AS test-runner
RUN pip install --no-cache-dir pytest==9.1.1
ENV PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 HOME=/tmp
USER 65532:65532
WORKDIR /workspace
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
