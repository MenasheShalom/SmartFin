FROM node:22-bookworm-slim

# System Chromium: works on arm64 (Raspberry Pi), unlike Puppeteer's bundled build
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium fonts-noto-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    SCRAPER_OUTPUT_DIR=/app/output \
    SCRAPER_ACCOUNTS_FILE=/app/config/accounts.json \
    TZ=Asia/Jerusalem

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY src ./src

CMD ["node", "src/main.js"]
