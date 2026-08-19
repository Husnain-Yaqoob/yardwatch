FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so a code change does not invalidate the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir prometheus-client

COPY yardwatch/ ./yardwatch/

EXPOSE 8000

CMD ["python", "-m", "yardwatch.exporter", "--port", "8000", "--capacity", "2"]
