# VantaHire — Railway Automation Service
# Runs the Python task runner that polls Supabase and applies to jobs.

FROM python:3.11-slim

# Install system dependencies required by Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget curl ca-certificates gnupg \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 \
    libxshmfence1 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    fonts-liberation libappindicator3-1 libx11-xcb1 libxcb-dri3-0 \
    xdg-utils --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only — smallest footprint)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy the full project
COPY . .

# Set PYTHONPATH so taskrunner can import from automation/
ENV PYTHONPATH=/app:/app/taskrunner

# Railway injects all env vars — no .env file needed at runtime
ENV PYTHONUNBUFFERED=1

# Start the task runner
CMD ["python", "taskrunner/main.py"]
