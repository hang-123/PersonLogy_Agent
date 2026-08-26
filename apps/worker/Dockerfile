FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace
COPY packages/personlogy_core ./packages/personlogy_core
COPY apps/worker ./apps/worker
WORKDIR /workspace/apps/worker
RUN pip install --no-cache-dir /workspace/packages/personlogy_core \
    && pip install --no-cache-dir .

CMD ["python", "-m", "personlogy_worker.main"]
