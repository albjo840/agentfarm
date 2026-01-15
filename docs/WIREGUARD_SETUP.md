# WireGuard + DuckDNS Setup Guide

> **Testad konfiguration** från fungerande system (2026-01-15)
>
> Se även: [INDEX.md](./INDEX.md) | [ROCM_SETUP.md](./ROCM_SETUP.md) | [SECURITY.md](./SECURITY.md)

## Översikt

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      WIREGUARD VPN SETUP                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Internet ──► DuckDNS (taborsen.duckdns.org)                           │
│                    │                                                    │
│                    ▼                                                    │
│              ┌─────────────┐                                           │
│              │ Port 51820  │ (UDP)                                     │
│              │  WireGuard  │                                           │
│              └─────────────┘                                           │
│                    │                                                    │
│                    ▼                                                    │
│              ┌─────────────┐         ┌─────────────┐                   │
│              │   wg0       │ ──────► │  enp7s0     │ ──► NAT ──► LAN  │
│              │ 10.0.0.1/24 │         │ Public IP   │                   │
│              └─────────────┘         └─────────────┘                   │
│                                                                         │
│  Peers:                                                                │
│  • 10.0.0.2 - Mobil/Laptop 1                                          │
│  • 10.0.0.3 - Mobil/Laptop 2                                          │
│  • 10.0.0.4 - ...                                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## System Specifikationer

| Komponent | Värde |
|-----------|-------|
| **Server IP** | 10.0.0.1/24 |
| **Port** | 51820/udp |
| **DuckDNS Domain** | taborsen.duckdns.org |
| **Network Interface** | enp7s0 |
| **SSH Port** | 2222 (ej standard för säkerhet) |

## Steg 1: Installera WireGuard

```bash
sudo apt update
sudo apt install -y wireguard wireguard-tools qrencode
```

## Steg 2: Generera Server Keys

```bash
# Skapa config directory
sudo mkdir -p /etc/wireguard
cd /etc/wireguard

# Generera server keys
wg genkey | sudo tee privatekey | wg pubkey | sudo tee publickey

# Sätt rättigheter
sudo chmod 600 privatekey
```

## Steg 3: Server Konfiguration

Skapa `/etc/wireguard/wg0.conf`:

```ini
[Interface]
Address = 10.0.0.1/24
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o enp7s0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o enp7s0 -j MASQUERADE
ListenPort = 51820
PrivateKey = <SERVER_PRIVATE_KEY>

# Lägg till peers nedan...
```

**OBS:** Byt ut `enp7s0` mot ditt nätverkskort (kolla med `ip link`).

## Steg 4: Aktivera IP Forwarding

```bash
# Temporärt
sudo sysctl -w net.ipv4.ip_forward=1

# Permanent
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

## Steg 5: Konfigurera Brandvägg (UFW)

```bash
# Tillåt WireGuard
sudo ufw allow 51820/udp comment "WireGuard VPN"

# Tillåt SSH (custom port)
sudo ufw allow 2222/tcp comment "SSH"

# Tillåt trafik från VPN-nät
sudo ufw allow from 10.0.0.0/24

# Aktivera
sudo ufw enable

# Verifiera
sudo ufw status
```

**Förväntad output:**
```
Status: active

To                         Action      From
--                         ------      ----
2222/tcp                   ALLOW       Anywhere         # SSH
51820/udp                  ALLOW       Anywhere         # WireGuard VPN
Anywhere                   ALLOW       10.0.0.0/24
```

## Steg 6: Starta WireGuard

```bash
# Starta
sudo systemctl start wg-quick@wg0

# Aktivera vid boot
sudo systemctl enable wg-quick@wg0

# Verifiera
sudo wg show
```

## Steg 7: DuckDNS Setup

### 7.1 Registrera Domain

1. Gå till https://www.duckdns.org/
2. Logga in med GitHub/Google
3. Skapa subdomain (t.ex. `taborsen`)
4. Kopiera din token

### 7.2 Skapa Update Script

```bash
mkdir -p ~/duckdns

cat > ~/duckdns/duck.sh << 'EOF'
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=taborsen&token=YOUR_TOKEN_HERE&ip=" | curl -k -o ~/duckdns/duck.log -K -
EOF

chmod +x ~/duckdns/duck.sh
```

**OBS:** Byt ut `taborsen` och `YOUR_TOKEN_HERE` mot dina värden.

### 7.3 Testa Scriptet

```bash
~/duckdns/duck.sh
cat ~/duckdns/duck.log
# Förväntat: OK
```

### 7.4 Lägg till Cron Job

```bash
crontab -e

# Lägg till denna rad (uppdaterar var 5:e minut):
*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1
```

## Steg 8: Lägg till Peers (Klienter)

### 8.1 Generera Peer Keys

På servern:
```bash
# Generera keys för ny peer
wg genkey | tee peer_privatekey | wg pubkey > peer_publickey
```

### 8.2 Lägg till Peer i Server Config

```bash
sudo tee -a /etc/wireguard/wg0.conf << EOF

[Peer]
PublicKey = $(cat peer_publickey)
AllowedIPs = 10.0.0.2/32
EOF
```

### 8.3 Skapa Klient-config

```ini
[Interface]
PrivateKey = <PEER_PRIVATE_KEY>
Address = 10.0.0.2/24
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = <SERVER_PUBLIC_KEY>
Endpoint = taborsen.duckdns.org:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
```

### 8.4 Generera QR-kod för Mobil

```bash
qrencode -t UTF8 < client.conf
# Eller:
qrencode -o client.png < client.conf
```

## Steg 9: Reload efter Ändringar

```bash
# Lägg till peer utan restart
sudo wg set wg0 peer <PEER_PUBLIC_KEY> allowed-ips 10.0.0.X/32

# Eller reload hela config
sudo wg syncconf wg0 <(wg-quick strip wg0)

# Full restart (om nödvändigt)
sudo systemctl restart wg-quick@wg0
```

---

## Komplett Server Config (Referens)

`/etc/wireguard/wg0.conf`:

```ini
[Interface]
Address = 10.0.0.1/24
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o enp7s0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o enp7s0 -j MASQUERADE
ListenPort = 51820
PrivateKey = <REDACTED>

[Peer]
PublicKey = b215vGPIvTQcEleEOcNuVQ/Pb7eq1zsQdoApCkODTTI=
AllowedIPs = 10.0.0.2/32

[Peer]
PublicKey = v5O1TwMF7tYfYnGz8JF8tJieRGFgVKxCRVoR0HrPhnA=
AllowedIPs = 10.0.0.3/32

[Peer]
PublicKey = FtYBkaK1AlkckDJoE+j1cE+YHwAK1tMKOTn9ZgCPXRM=
AllowedIPs = 10.0.0.4/32

[Peer]
PublicKey = 3VO6v7q+CPbBj6t/ykIkNaW2LRrcD/lmhKL+BT4W9yI=
AllowedIPs = 10.0.0.5/32
```

---

## API Endpoint för Nya Peers

AgentFarm har en inbyggd endpoint för att generera nya peers:

```bash
# POST /api/wireguard/new-peer
curl -X POST http://10.0.0.1:8080/api/wireguard/new-peer
```

Returnerar:
```json
{
  "success": true,
  "ip": "10.0.0.6",
  "qr_text": "...",
  "config": "[Interface]\nPrivateKey = ...\n..."
}
```

Se `src/agentfarm/web/server.py:api_wireguard_qr_handler`

---

## Felsökning

### Kan inte ansluta

```bash
# Kolla att WireGuard körs
sudo wg show

# Kolla att port är öppen
sudo netstat -ulnp | grep 51820

# Kolla brandvägg
sudo ufw status

# Kolla logs
sudo journalctl -u wg-quick@wg0
```

### DuckDNS uppdateras inte

```bash
# Testa manuellt
~/duckdns/duck.sh
cat ~/duckdns/duck.log

# Kolla cron
crontab -l | grep duck
```

### Peers kan inte nå internet

```bash
# Kolla IP forwarding
cat /proc/sys/net/ipv4/ip_forward
# Ska vara: 1

# Kolla NAT-regler
sudo iptables -t nat -L -n | grep MASQUERADE
```

---

## Snabbinstallation (Copy-Paste)

```bash
#!/bin/bash
# WireGuard + DuckDNS Quick Setup

set -e

# Variabler - ÄNDRA DESSA!
DUCKDNS_DOMAIN="taborsen"
DUCKDNS_TOKEN="your-token-here"
INTERFACE="enp7s0"  # Kolla med: ip link

# 1. Installera
sudo apt update
sudo apt install -y wireguard wireguard-tools qrencode

# 2. Generera server keys
sudo mkdir -p /etc/wireguard
wg genkey | sudo tee /etc/wireguard/privatekey | wg pubkey | sudo tee /etc/wireguard/publickey
sudo chmod 600 /etc/wireguard/privatekey

# 3. Skapa config
sudo tee /etc/wireguard/wg0.conf << EOF
[Interface]
Address = 10.0.0.1/24
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ${INTERFACE} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ${INTERFACE} -j MASQUERADE
ListenPort = 51820
PrivateKey = $(sudo cat /etc/wireguard/privatekey)
EOF

# 4. IP forwarding
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# 5. Brandvägg
sudo ufw allow 51820/udp comment "WireGuard VPN"
sudo ufw allow from 10.0.0.0/24

# 6. Starta WireGuard
sudo systemctl enable --now wg-quick@wg0

# 7. DuckDNS
mkdir -p ~/duckdns
cat > ~/duckdns/duck.sh << EOF
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=" | curl -k -o ~/duckdns/duck.log -K -
EOF
chmod +x ~/duckdns/duck.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -

# 8. Testa
~/duckdns/duck.sh
sudo wg show

echo "=== Server Public Key ==="
sudo cat /etc/wireguard/publickey
echo ""
echo "=== Klar! Endpoint: ${DUCKDNS_DOMAIN}.duckdns.org:51820 ==="
```

---

*Dokumenterad från fungerande system 2026-01-15*
