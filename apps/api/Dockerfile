FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace
COPY packages/personlogy_core ./packages/personlogy_core
COPY apps/api ./apps/api
WORKDIR /workspace/apps/api
RUN pip install --no-cache-dir /workspace/packages/personlogy_core \
    && pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
