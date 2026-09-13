FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so a code change does not invalidate the pip layer.
#
# Only prometheus-client, deliberately. This image runs one module. Installing
# the project's full dependency set would pull matplotlib in to sit unused, for
# an image several times the size.
RUN pip install --no-cache-dir "prometheus-client>=0.20"

COPY yardwatch/ ./yardwatch/

EXPOSE 8000

CMD ["python", "-m", "yardwatch.exporter", "--port", "8000", "--capacity", "2"]
