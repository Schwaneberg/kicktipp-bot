# Docker Deployment Guide for x86 NAS

This guide explains how to deploy the Kicktipp Bot on your x86-based NAS using Docker.

## Prerequisites

- Docker installed on your NAS
- Docker Compose installed (optional but recommended)
- A `.env` file configured with your Kicktipp credentials and settings

## Quick Start

### 1. Prepare your `.env` file

Copy `.env.example` to `.env` and fill in your settings:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```dotenv
KICKTIPP_EMAIL=your-email@example.com
KICKTIPP_PASSWORD=your-password
KICKTIPP_COMPETITIONS=liga-eins,liga-zwei
OPENAI_API_KEY=sk-your-key-here
PREDICTOR=ai
```

### 2. Build the Docker image

```bash
# From the project root directory
docker build -f docker/Dockerfile.x86 -t kicktipp-bot:latest .
```

### 3. Run with Docker Compose (Recommended)

```bash
# From docker directory
cd docker
docker-compose -f docker-compose.x86.yml up -d
```

### 4. Run with Docker CLI (Alternative)

```bash
docker run -d \
  --name kicktipp-bot \
  --restart unless-stopped \
  --env-file .env \
  -p 8080:8080 \
  -v kicktipp-logs:/app/logs \
  kicktipp-bot:latest
```

## Managing the Container

### View logs
```bash
# With Docker Compose
docker-compose -f docker/docker-compose.x86.yml logs -f kicktipp-bot

# With Docker CLI
docker logs -f kicktipp-bot
```

### Stop the container
```bash
# With Docker Compose
docker-compose -f docker/docker-compose.x86.yml down

# With Docker CLI
docker stop kicktipp-bot
```

### Restart the container
```bash
# With Docker Compose
docker-compose -f docker/docker-compose.x86.yml restart

# With Docker CLI
docker restart kicktipp-bot
```

### Health check
```bash
curl http://localhost:8080/health
```

## Environment Variables

All standard environment variables from `.env.example` are supported:

- `KICKTIPP_EMAIL` - Your Kicktipp email (required)
- `KICKTIPP_PASSWORD` - Your Kicktipp password (required)
- `KICKTIPP_COMPETITIONS` - Comma-separated list of competitions
- `PREDICTOR` - `ai` or `quotes` (default: ai)
- `OPENAI_API_KEY` - Required when PREDICTOR=ai
- `OPENAI_MODEL` - OpenAI model to use (default: gpt-5.5)
- `KICKTIPP_HOURS_UNTIL_GAME` - Hours threshold for tipping (default: 2)
- `KICKTIPP_RUN_EVERY_X_MINUTES` - Run interval (default: 60)
- `OVERWRITE_TIPS` - Overwrite existing tips (default: false)
- `GROUP_NOTIFICATIONS` - Group notifications (default: false)
- `TZ` - Timezone (default: Europe/Berlin)

### Notifications (Optional)

- `ZAPIER_URL` - Zapier webhook URL
- `NTFY_URL`, `NTFY_USERNAME`, `NTFY_PASSWORD` - ntfy.sh integration
- `WEBHOOK_URL` - Generic webhook URL

### Error Reporting (Optional)

- `SENTRY_DSN` - Sentry error tracking
- `SENTRY_ENVIRONMENT` - Sentry environment

## Resource Recommendations

For x86 NAS deployments, the Docker Compose file limits resources to:
- **CPU**: 2 cores max, 1 core reserved
- **Memory**: 2GB max, 1GB reserved

Adjust these limits in `docker-compose.x86.yml` based on your NAS capabilities:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
```

## Troubleshooting

### Container exits immediately
Check the logs:
```bash
docker logs kicktipp-bot
```

Most likely causes:
- Missing or invalid `.env` file
- Invalid KICKTIPP_EMAIL or KICKTIPP_PASSWORD
- Missing OPENAI_API_KEY when PREDICTOR=ai

### Chromium not found
This image uses Debian slim with Chromium pre-installed. If you see Chrome errors:
```bash
# Ensure the image was built with the latest Dockerfile.x86
docker build -f docker/Dockerfile.x86 -t kicktipp-bot:latest --no-cache .
```

### High memory usage
Reduce resource limits in `docker-compose.x86.yml` or increase NAS swap.

## Advanced: Building multi-platform images

To build for multiple architectures:

```bash
docker buildx build \
  -f docker/Dockerfile.x86 \
  -t kicktipp-bot:latest \
  --platform linux/amd64,linux/arm64 \
  .
```

## Notes

- The container runs in headless mode (no GUI) with Chromium driver
- Health checks occur every 30 seconds
- Logs are stored locally and rotated (max 10MB per file, 3 files kept)
- The bot respects all Kicktipp rate limits and timing windows
