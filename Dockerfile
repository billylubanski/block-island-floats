FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    WEB_CONCURRENCY=2 \
    GUNICORN_TIMEOUT=120 \
    GUNICORN_GRACEFUL_TIMEOUT=30 \
    GUNICORN_LOG_LEVEL=info

WORKDIR /app

COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
