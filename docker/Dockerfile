# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS runtime

# 依赖源：默认使用腾讯云镜像，可通过 --build-arg 覆盖。
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.cloud.tencent.com

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PYTHONPATH=/app

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

# 仅复制依赖声明，业务代码变更不会触发依赖重装。
COPY backend/pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip pip install .

COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY --chmod=755 docker/entrypoint.sh /app/entrypoint.sh

RUN mkdir -p /app/media && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:8000", "--workers", "8", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "3600", "--access-logfile", "-", "--error-logfile", "-"]
