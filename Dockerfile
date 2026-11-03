# Una sola imagen para API, worker y migraciones: cambia solo el comando.
FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision=$GIT_SHA \
      org.opencontainers.image.title="notifier"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NOTIFIER_GIT_SHA=$GIT_SHA
COPY --from=build /install /usr/local
RUN useradd --system --uid 10001 --no-create-home app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "notifier.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
# Worker:      python -m notifier.worker.main
# Migraciones: python -m notifier.migrate
