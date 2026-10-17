FROM python:3.12-slim

WORKDIR /app

# LightGBM needs libgomp
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY models ./models
COPY data ./data

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/data/bot.db

# Persist SQLite across restarts when a volume is mounted at /data
RUN mkdir -p /data

CMD ["python", "-m", "src.bot.app"]
