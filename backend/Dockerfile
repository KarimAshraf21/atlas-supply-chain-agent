FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/pyproject.toml backend/
COPY backend/atlas backend/atlas
RUN pip install --no-cache-dir ./backend

COPY data data
COPY backend/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV SEED_DIR=/app/data/seed
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
