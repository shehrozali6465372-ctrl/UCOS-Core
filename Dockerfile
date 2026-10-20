FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app
EXPOSE 8000
USER 10001:10001
CMD ["sh", "-c", "python -m ucos_core.preflight && exec uvicorn ucos_core.main:app --host 0.0.0.0 --port 8000"]
