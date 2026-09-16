FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends adb curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY artemis_mobile_agent ./artemis_mobile_agent
RUN pip install --no-cache-dir .
ENV ARTEMIS_TRACE_DIR=/data/traces PORT=8000
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD curl -fsS http://127.0.0.1:${PORT}/health || exit 1
CMD ["sh", "-c", "artemis-mobile serve --host 0.0.0.0 --port ${PORT}"]
