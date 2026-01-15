# AgentFarm Deployment Guide

Production deployment using Docker Compose, Nginx, and Let's Encrypt SSL.

## Prerequisites

- **Ubuntu 22.04 LTS** (required for ROCm compatibility)
- Docker and Docker Compose
- A domain name pointing to your server
- At least one LLM API key (Groq, Gemini, or SiliconFlow for free tiers)

## Quick Start

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group changes
```

### 2. Clone and Configure

```bash
git clone https://github.com/your/agentfarm.git
cd agentfarm/deploy

# Copy environment template
cp .env.example .env

# Edit with your API keys and domain
nano .env
```

### 3. Update Nginx Config

Edit `nginx/conf.d/agentfarm.conf` and replace `agentfarm.example.com` with your actual domain:

```bash
sed -i 's/agentfarm.example.com/your-domain.com/g' nginx/conf.d/agentfarm.conf
```

### 4. Get SSL Certificate

First, start nginx without SSL to complete the ACME challenge:

```bash
# Create temporary HTTP-only config
cat > nginx/conf.d/temp.conf << 'EOF'
server {
    listen 80;
    server_name your-domain.com;
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 200 'OK';
    }
}
EOF

# Start nginx
docker compose up -d nginx

# Get certificate
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    -d your-domain.com \
    --email your@email.com \
    --agree-tos \
    --no-eff-email

# Remove temporary config
rm nginx/conf.d/temp.conf

# Restart with full config
docker compose down
```

### 5. Start Production Stack

```bash
docker compose up -d
```

### 6. Verify

```bash
# Check status
docker compose ps

# View logs
docker compose logs -f agentfarm

# Test health
curl https://your-domain.com/health
```

## Architecture

```
Internet
    |
    v
+-------------------+
|   Nginx (443)     |  SSL termination, rate limiting
+-------------------+
    |
    v
+-------------------+
|   AgentFarm App   |  Python aiohttp server
|   (port 8080)     |
+-------------------+
    |
    v
+-------------------+
|   Volumes         |
|   - .agentfarm/   |  Config, analytics, workflows
|   - projects/     |  Generated projects
+-------------------+
```

## Development Mode

For local development without SSL:

```bash
docker compose -f docker-compose.dev.yml up -d
# Access at http://localhost:8080
```

## Proxmox Setup

If running on Proxmox, create a dedicated VM:

```bash
# On Proxmox host
qm create 100 --name agentfarm-prod --memory 4096 --cores 2 --net0 virtio,bridge=vmbr0

# Use Ubuntu 22.04 LTS cloud image (REQUIRED for ROCm)
# Debian 12 is NOT supported for ROCm
```

## Stripe Webhooks

After deployment, configure Stripe webhooks:

1. Go to https://dashboard.stripe.com/webhooks
2. Add endpoint: `https://your-domain.com/webhook/stripe`
3. Select events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
4. Copy webhook secret to `.env`

## Affiliate Setup

1. Apply for affiliate programs:
   - Dustin: https://www.dustin.se/service/affiliate
   - Komplett: https://www.komplett.se/affiliate
   - Inet: https://www.inet.se/affiliate
   - Electrokit: Contact directly
   - Amazon.se: https://affiliate-program.amazon.se

2. Update `.agentfarm/affiliates.json` with your affiliate parameters

## Maintenance

### View Logs
```bash
docker compose logs -f agentfarm
docker compose logs -f nginx
```

### Restart Services
```bash
docker compose restart agentfarm
```

### Update Application
```bash
git pull
docker compose build agentfarm
docker compose up -d agentfarm
```

### SSL Certificate Renewal
Certbot automatically renews certificates. To force renewal:
```bash
docker compose run --rm certbot renew --force-renewal
docker compose restart nginx
```

### Backup Data
```bash
# Backup volumes
docker run --rm -v agentfarm_data:/data -v $(pwd):/backup alpine \
    tar czf /backup/agentfarm-data-$(date +%Y%m%d).tar.gz /data
```

## Troubleshooting

### Port 80/443 already in use
```bash
sudo lsof -i :80
sudo lsof -i :443
# Stop conflicting service or change ports
```

### SSL certificate issues
```bash
# Check certificate
docker compose run --rm certbot certificates

# View nginx SSL errors
docker compose logs nginx | grep -i ssl
```

### WebSocket connection fails
Check nginx WebSocket configuration and ensure `/ws` location block is correct.

### Rate limiting too strict
Adjust `limit_req_zone` values in `nginx/nginx.conf` and restart nginx.
