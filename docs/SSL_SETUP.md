# SSL/TLS Setup för AgentFarm

> Se även: [SECURITY.md](./SECURITY.md) | [ARCHITECTURE.md](./ARCHITECTURE.md)

## Översikt

AgentFarm använder Let's Encrypt SSL-certifikat via Certbot för HTTPS.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRAFFIC FLOW                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Stripe Webhooks:                                                       │
│  Stripe → HTTPS → agentfarm.se:443 → nginx → localhost:8080            │
│                                                                         │
│  Web Interface:                                                         │
│  Browser → HTTPS → agentfarm.se:443 → nginx → localhost:8080           │
│           (eller taborsen.duckdns.org:443)                             │
│                                                                         │
│  WebSocket:                                                             │
│  Browser → WSS → agentfarm.se:443 → nginx → localhost:8080/ws          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Domäner

| Domän | DNS Provider | IP | Certifikat |
|-------|--------------|-----|------------|
| agentfarm.se | Loopia | 31.208.228.229 | Let's Encrypt (webroot) |
| taborsen.duckdns.org | DuckDNS | 31.208.228.229 | Let's Encrypt (DNS-01) |

## Certbot Installation

Certbot är installerat via snap (rekommenderat):

```bash
# Installation
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot

# DuckDNS plugin för DNS-01 challenge
sudo snap install certbot-dns-duckdns
sudo snap set certbot trust-plugin-with-root=ok
sudo snap connect certbot:plugin certbot-dns-duckdns
```

## Certifikat

### agentfarm.se

Använder webroot challenge:

```bash
sudo certbot certonly --webroot \
    --webroot-path=/var/www/html \
    -d agentfarm.se \
    --email albjo840@gmail.com \
    --agree-tos --non-interactive
```

### taborsen.duckdns.org

Använder DNS-01 challenge via DuckDNS API:

```bash
# Credentials fil
sudo mkdir -p /etc/letsencrypt/duckdns
sudo tee /etc/letsencrypt/duckdns/credentials.ini << 'EOF'
dns_duckdns_token = <DUCKDNS_TOKEN>
EOF
sudo chmod 600 /etc/letsencrypt/duckdns/credentials.ini

# Hämta certifikat
sudo certbot certonly \
    --authenticator dns-duckdns \
    --dns-duckdns-credentials /etc/letsencrypt/duckdns/credentials.ini \
    --dns-duckdns-propagation-seconds 180 \
    -d taborsen.duckdns.org \
    --email albjo840@gmail.com \
    --agree-tos --non-interactive
```

## nginx Konfiguration

### agentfarm.se

Fil: `/etc/nginx/sites-available/agentfarm.se`

```nginx
server {
    server_name agentfarm.se www.agentfarm.se;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/agentfarm.se/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agentfarm.se/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    listen 80;
    server_name agentfarm.se www.agentfarm.se;
    return 301 https://$host$request_uri;
}
```

### taborsen.duckdns.org

Fil: `/etc/nginx/sites-available/taborsen`

```nginx
server {
    listen 80;
    server_name taborsen.duckdns.org;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name taborsen.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/taborsen.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/taborsen.duckdns.org/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    location /webhook/stripe {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass_request_body on;
    }
}
```

## Auto-Renewal

Certbot snap installerar automatisk förnyelse via systemd timer:

```bash
# Kolla status
sudo systemctl status snap.certbot.renew.timer

# Testa förnyelse manuellt
sudo certbot renew --dry-run

# Renewal hook för nginx reload
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh << 'EOF'
#!/bin/bash
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

## Verifiering

```bash
# Kolla certifikat
sudo certbot certificates

# Testa HTTPS
curl -I https://agentfarm.se
curl -I https://taborsen.duckdns.org

# Kolla certifikat-detaljer
echo | openssl s_client -connect agentfarm.se:443 2>/dev/null | openssl x509 -noout -dates

# Testa HTTP→HTTPS redirect
curl -I http://agentfarm.se
```

## Felsökning

### DNS-problem med DuckDNS

Om certbot misslyckas med "SERVFAIL" eller "query timed out":

1. Verifiera DuckDNS token
2. Öka propagation time: `--dns-duckdns-propagation-seconds 300`
3. Testa DuckDNS API manuellt:
   ```bash
   curl "https://www.duckdns.org/update?domains=taborsen&token=<TOKEN>&txt=test"
   dig TXT _acme-challenge.taborsen.duckdns.org +short
   ```

### Certbot broken (apt version)

Om apt-installerad certbot ger Python-fel:

```bash
sudo apt remove certbot -y
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot
```

### nginx testar inte OK

```bash
sudo nginx -t
# Kolla syntax och paths
```

## Viktiga filer

| Fil | Beskrivning |
|-----|-------------|
| `/etc/letsencrypt/live/*/fullchain.pem` | Certifikat + chain |
| `/etc/letsencrypt/live/*/privkey.pem` | Privat nyckel |
| `/etc/letsencrypt/renewal/*.conf` | Renewal-konfiguration |
| `/etc/letsencrypt/duckdns/credentials.ini` | DuckDNS token |
| `/etc/nginx/sites-available/*` | nginx vhost configs |
| `/var/log/letsencrypt/letsencrypt.log` | Certbot logg |

---

*Senast uppdaterad: 2026-01-22*
