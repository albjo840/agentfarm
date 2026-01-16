# Network Isolation - Dual Interface Setup

> **Mål:** Separera extern trafik (WireGuard) från intern LLM-trafik
>
> Se även: [WIREGUARD_SETUP.md](./WIREGUARD_SETUP.md) | [SECURITY.md](./SECURITY.md)

## Arkitektur

```
Internet ←→ Router ←→ Proxmox Host
                          │
                    ┌─────┴─────┐
                    │           │
               vmbr0 (WAN)  vmbr1 (LAN)
              10.0.0.0/24   192.168.100.0/24
                    │           │
              ┌─────┴─────┐     │
              │           │     │
         WireGuard    AgentFarm │
           Peers        VM      │
                    ┌───────────┘
                    │
              Ollama VM
           (Ingen internet)
```

## Nätverkssegment

| Bridge | Subnet | Syfte | Internet |
|--------|--------|-------|----------|
| **vmbr0** | 10.0.0.0/24 | WireGuard VPN | Ja |
| **vmbr1** | 192.168.100.0/24 | Intern LLM-trafik | Nej |

## Steg 1: Skapa Bridges i Proxmox

### 1.1 vmbr0 - Extern (WAN)

Redan konfigurerad som standard. Ansluten till fysiskt interface.

```bash
# /etc/network/interfaces
auto vmbr0
iface vmbr0 inet static
    address 10.0.0.1/24
    bridge-ports enp1s0
    bridge-stp off
    bridge-fd 0
```

### 1.2 vmbr1 - Intern (LAN, ingen internet)

```bash
# Lägg till i /etc/network/interfaces
auto vmbr1
iface vmbr1 inet static
    address 192.168.100.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    # Ingen gateway = ingen internetåtkomst
```

Aktivera:

```bash
systemctl restart networking
# eller
ifup vmbr1
```

## Steg 2: VM-konfiguration

### AgentFarm VM (Web + Orchestrator)

Dubbla nätverksinterface:

```bash
# I Proxmox VM config (t.ex. /etc/pve/qemu-server/101.conf)
net0: virtio=XX:XX:XX:XX:XX:XX,bridge=vmbr0
net1: virtio=YY:YY:YY:YY:YY:YY,bridge=vmbr1
```

I Ubuntu VM:

```bash
# /etc/netplan/00-installer-config.yaml
network:
  version: 2
  ethernets:
    ens18:
      addresses:
        - 10.0.0.10/24
      routes:
        - to: default
          via: 10.0.0.1
      nameservers:
        addresses:
          - 1.1.1.1
          - 8.8.8.8
    ens19:
      addresses:
        - 192.168.100.10/24
      # Ingen default route - endast lokal trafik
```

Aktivera:

```bash
sudo netplan apply
```

### Ollama VM (LLM Server)

Endast internt interface - ingen internetåtkomst:

```bash
# I Proxmox VM config
net0: virtio=ZZ:ZZ:ZZ:ZZ:ZZ:ZZ,bridge=vmbr1
```

I Ubuntu VM:

```bash
# /etc/netplan/00-installer-config.yaml
network:
  version: 2
  ethernets:
    ens18:
      addresses:
        - 192.168.100.20/24
      # Ingen routes, ingen DNS - helt isolerad
```

## Steg 3: Brandväggsregler (iptables)

På Proxmox host, skapa `/etc/pve/firewall/cluster.fw`:

```ini
[OPTIONS]
enable: 1

[RULES]
# Tillåt SSH till host
IN ACCEPT -p tcp --dport 22

# Tillåt WireGuard
IN ACCEPT -p udp --dport 51820

# Tillåt inkommande på vmbr0 (WireGuard)
IN ACCEPT -i vmbr0

# Blockera routing mellan vmbr0 och vmbr1
# (Förhindra WireGuard-klienter från att nå Ollama direkt)
FORWARD DROP -i vmbr0 -o vmbr1
```

### Alternativ: iptables manuellt

```bash
# Tillåt traffic på vmbr1 (intern)
iptables -A FORWARD -i vmbr1 -o vmbr1 -j ACCEPT

# Blockera vmbr1 från internet
iptables -A FORWARD -i vmbr1 -o vmbr0 -j DROP
iptables -A FORWARD -i vmbr0 -o vmbr1 -j DROP

# Spara regler
iptables-save > /etc/iptables/rules.v4
```

## Steg 4: Verifiera Isolering

### Från AgentFarm VM

```bash
# Ska fungera (internet via vmbr0)
ping 8.8.8.8

# Ska fungera (Ollama via vmbr1)
curl http://192.168.100.20:11434/api/tags
```

### Från Ollama VM

```bash
# Ska INTE fungera (ingen internetåtkomst)
ping 8.8.8.8
# ping: connect: Network is unreachable

# Ska fungera (intern kommunikation)
ping 192.168.100.10
```

### Från WireGuard-klient

```bash
# Ska fungera (AgentFarm web)
curl http://10.0.0.10:8080

# Ska INTE fungera (Ollama är isolerad)
curl http://192.168.100.20:11434
# Connection refused
```

## AgentFarm Konfiguration

### Ollama URL

I `.env` eller miljövariabler på AgentFarm VM:

```bash
# Använd internt IP för Ollama
OLLAMA_HOST=http://192.168.100.20:11434
```

### Web Server

```bash
# Lyssna på WireGuard-interface
agentfarm web --host 10.0.0.10 --port 8080
```

## Diagram: Trafikflöde

```
WireGuard Client (10.0.0.X)
    │
    │ ── VPN-tunnel ──
    │
    ▼
Proxmox Host (10.0.0.1)
    │
    ├─── vmbr0 ───► AgentFarm VM (10.0.0.10)
    │                    │
    │                    │ ens19 (192.168.100.10)
    │                    ▼
    └─── vmbr1 ───► Ollama VM (192.168.100.20)
                   [INGEN INTERNET]
```

## Fördelar med denna setup

1. **Säkerhet**: Ollama-servern har ingen internetåtkomst, kan inte exfiltrera data
2. **Prestanda**: Intern trafik går direkt via bridge, ingen NAT
3. **Enkel åtkomst**: WireGuard-klienter kommer åt AgentFarm web
4. **Isolering**: LLM-trafik är helt separerad från extern trafik

## Felsökning

### VM når inte internet

```bash
# Kontrollera routing
ip route

# Kontrollera DNS
cat /etc/resolv.conf
```

### VMs når inte varandra på vmbr1

```bash
# Kontrollera att bridge finns
brctl show vmbr1

# Kontrollera IP-konfiguration
ip addr show
```

### WireGuard-klienter kan nå Ollama

```bash
# Kontrollera brandväggsregler
iptables -L FORWARD -v -n

# Lägg till blockeringsregel
iptables -I FORWARD -s 10.0.0.0/24 -d 192.168.100.0/24 -j DROP
```

---

*Guide skapad 2026-01-16. Testad med Proxmox 8.1, Ubuntu 22.04 VMs.*
