FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements-runtime.txt ./requirements-runtime.txt
RUN python -m pip install -r requirements-runtime.txt && python -m pip check
RUN useradd --create-home --uid 10001 support && mkdir -p /data && chown support:support /data
COPY backend/*.py ./
COPY knowledge_base/ /app/knowledge_base/
USER support
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
