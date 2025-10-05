FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY app /app/app

# Create data directory for SQLite ledger (mount a volume at /data in production)
VOLUME ["/data"]

# Default environment (override as needed)
ENV BANKROLL=500 \
    MIN_EDGE=0.03 \
    MIN_EDGE_ML=0.03 \
    KELLY_FRACTION=0.5 \
    MAX_UNIT=0.02 \
    WEEKDAY_RUN_TIME=09:00 \
    SUNDAY_RUN_TIME=12:00

CMD ["python", "-m", "app.main"]

