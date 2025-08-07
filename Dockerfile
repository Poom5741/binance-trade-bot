FROM --platform=$BUILDPLATFORM python:3.8 as builder

WORKDIR /install

RUN apt-get update && apt-get install -y rustc

COPY requirements.txt /requirements.txt
RUN pip install --prefix=/install -r /requirements.txt

FROM python:3.8-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

# Default backup directory used by BackupManager
ENV BACKUP_DIR=/app/backups \
    BACKUP_INTERVAL=3600

# Ensure backup directory exists
RUN mkdir -p $BACKUP_DIR

# Basic health check verifying that the Python interpreter starts
HEALTHCHECK CMD ["python", "-c", "import sqlite3"]

CMD ["python", "-m", "binance_trade_bot"]
