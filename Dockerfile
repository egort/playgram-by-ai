# Base image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies for uvloop/httptools and clean up
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY favicon.ico /app/favicon.ico
COPY favicon.svg /app/favicon.svg

# Install project in editable mode so packaged static files are available
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Optional: drop build deps (kept minimal already)

EXPOSE 8000

CMD ["python", "-m", "playgram"]
