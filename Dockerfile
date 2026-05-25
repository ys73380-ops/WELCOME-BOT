# ---- Base Image ----
FROM python:3.11-slim

# ---- Environment ----
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- Working Directory ----
WORKDIR /app

# ---- Install Dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Copy Source ----
COPY bot.py .

# ---- Data Volume (JSON persistence) ----
VOLUME ["/app/data"]

# ---- Health Check (port 8080) ----
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080')" || exit 1

# ---- Expose Health Port ----
EXPOSE 8080

# ---- Run ----
CMD ["python", "bot.py"]
