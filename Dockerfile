FROM python:3.11-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[server]"

FROM python:3.11-slim AS runtime

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/alembic /usr/local/bin/
COPY src/ src/
COPY alembic.ini .

EXPOSE 8000

CMD ["uvicorn", "sessionfs.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
