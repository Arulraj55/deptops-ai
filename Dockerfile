FROM python:3.11-slim

# Install system packages required for Playwright and common Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libxss1 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libgtk-3-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . /app

# Upgrade pip and install Python deps
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# Install Playwright browsers (requires the system deps installed above)
RUN playwright install --with-deps || true

# Ensure start script is executable
RUN chmod +x /app/start.sh

ENV PORT=8000
EXPOSE ${PORT}

CMD ["/app/start.sh"]
