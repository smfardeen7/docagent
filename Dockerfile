# Same image runs the API (default CMD) and the worker (`arq docagent.worker.main.WorkerSettings`).
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    DOCAGENT_DATA_DIR=/data
WORKDIR /app
RUN pip install --no-cache-dir uv==0.9.5 \
    && adduser --disabled-password --gecos "" app \
    && mkdir -p /data /models && chown app:app /data /models
# CPU-only torch keeps the image a few hundred MB instead of several GB. One lockfile per architecture:
# requirements-cpu.txt (x86_64: CI, cloud) and requirements-cpu-arm64.txt (Apple-silicon Docker, Graviton).
ARG TARGETARCH
COPY requirements-cpu.txt requirements-cpu-arm64.txt ./
# unsafe-best-match: the lockfiles pin exact versions across the PyTorch CPU index and PyPI, so there is no
# dependency-confusion surface for uv's first-index default to protect against.
RUN if [ "$TARGETARCH" = "arm64" ]; then LOCK=requirements-cpu-arm64.txt; else LOCK=requirements-cpu.txt; fi \
    && uv pip install --system --no-cache --index-strategy unsafe-best-match -r "$LOCK"
COPY pyproject.toml README.md ./
COPY docagent ./docagent
RUN uv pip install --system --no-cache --no-deps -e .
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=30 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=4).status==200 else 1)"
CMD ["uvicorn", "docagent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
