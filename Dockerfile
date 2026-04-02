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
    xdg-utils \
    xvfb x11vnc novnc websockify \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only — smallest footprint)
# Note: system deps already installed via apt-get above; skip install-deps
# to avoid failures on Debian Trixie (missing ttf-ubuntu-font-family etc.)
RUN playwright install chromium

# Copy the full project
COPY . .

# Set PYTHONPATH so taskrunner can import from automation/
ENV PYTHONPATH=/app:/app/taskrunner

# Railway injects all env vars — no .env file needed at runtime
ENV PYTHONUNBUFFERED=1

# Virtual display for headed Chromium on Railway (Xvfb started by server.py on boot)
ENV DISPLAY=:99

# Persistent browser profiles.
# Default: /tmp/sessions (works without a volume — ephemeral per container).
# With Railway volume: set SESSION_DIR=/sessions in Railway Variables and mount at /sessions.
ENV SESSION_DIR=/tmp/sessions
RUN mkdir -p /tmp/sessions

# Start the HTTP server (also boots the polling loop in a background thread)
CMD ["python", "taskrunner/server.py"]
