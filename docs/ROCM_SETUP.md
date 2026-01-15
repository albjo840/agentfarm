# ROCm + Ollama Setup Guide

> **Testad konfiguration** från fungerande system (2026-01-15)
>
> Se även: [INDEX.md](./INDEX.md) | [SECURITY.md](./SECURITY.md)

## System Specifikationer

| Komponent | Version/Värde |
|-----------|---------------|
| **OS** | Ubuntu 22.04.5 LTS (Jammy) |
| **Kernel** | 6.8.0-90-generic |
| **ROCm** | 6.4.3-128 |
| **GPU** | AMD Radeon RX 7800 XT (gfx1101) |
| **VRAM** | 16 GB |
| **Ollama** | Senaste (via install script) |

## Steg 1: Förbered Systemet

```bash
# Uppdatera systemet
sudo apt update && sudo apt upgrade -y

# Installera dependencies
sudo apt install -y wget gnupg2 software-properties-common

# Lägg till användare i nödvändiga grupper
sudo usermod -aG video,render $USER
# OBS: Logga ut och in igen efter detta!
```

## Steg 2: Installera ROCm 6.4.3

### 2.1 Lägg till ROCm Repository

```bash
# Skapa keyrings directory
sudo mkdir -p /etc/apt/keyrings

# Ladda ner och installera GPG-nyckel
wget https://repo.radeon.com/rocm/rocm.gpg.key -O - | \
    gpg --dearmor | sudo tee /etc/apt/keyrings/rocm.gpg > /dev/null

# Lägg till AMDGPU repository
echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/amdgpu/6.4.3/ubuntu jammy main" | \
    sudo tee /etc/apt/sources.list.d/amdgpu.list

# Uppdatera apt
sudo apt update
```

### 2.2 Installera ROCm Packages

```bash
# Installera ROCm ML SDK (innehåller allt som behövs för AI/ML)
sudo apt install -y rocm-ml-sdk

# Alternativt: minimal installation
# sudo apt install -y rocm-hip-sdk rocm-opencl-sdk
```

### 2.3 Verifiera Installation

```bash
# Kolla ROCm version
cat /opt/rocm/.info/version
# Förväntat: 6.4.3-128

# Kolla GPU-info
rocm-smi --showproductname
# Förväntat: AMD Radeon RX 7800 XT

# Kolla att GPU syns
rocminfo | grep "gfx"
# Förväntat: gfx1101
```

## Steg 3: Miljövariabler

**VIKTIGT för gfx1101 (RDNA 3):**

```bash
# Lägg till i /etc/environment eller ~/.bashrc
export HSA_OVERRIDE_GFX_VERSION=11.0.0
export HIP_VISIBLE_DEVICES=0
```

Eller skapa `/etc/profile.d/rocm.sh`:

```bash
sudo tee /etc/profile.d/rocm.sh << 'EOF'
export HSA_OVERRIDE_GFX_VERSION=11.0.0
export HIP_VISIBLE_DEVICES=0
export PATH=$PATH:/opt/rocm/bin
EOF
```

## Steg 4: Installera Ollama

```bash
# Installera Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Lägg till användare i ollama-gruppen
sudo usermod -aG ollama $USER
```

### 4.1 Konfigurera Ollama Service

Skapa override för att lyssna på alla interface:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d

sudo tee /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

# Ladda om och starta om
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama
```

### 4.2 Ollama Service File (referens)

`/etc/systemd/system/ollama.service`:

```ini
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin"

[Install]
WantedBy=default.target
```

## Steg 5: Ladda ner Modeller

```bash
# Rekommenderade modeller för AgentFarm
ollama pull qwen2.5-coder:7b    # Kod-generering (4.7 GB)
ollama pull qwen3:14b           # Komplex reasoning (9.3 GB)
ollama pull phi4                # Kod + matematik (9.1 GB)
ollama pull gemma2:9b           # Verifiering (5.4 GB)
ollama pull mistral-nemo        # Svenska/planering (7.1 GB)
ollama pull nemotron-mini       # Snabba svar (2.7 GB)
ollama pull llama3.2            # Generellt (2.0 GB)

# Verifiera
ollama list
```

## Steg 6: Verifiera GPU-användning

```bash
# Kolla att Ollama använder GPU
ollama run llama3.2 "Hello"

# I en annan terminal, övervaka GPU
watch -n 1 rocm-smi

# Du bör se VRAM-användning öka under inference
```

## Felsökning

### GPU syns inte i ROCm

```bash
# Kolla kernel module
lsmod | grep amdgpu
# Om tom, ladda modulen:
sudo modprobe amdgpu

# Kolla dmesg för fel
dmesg | grep -i amdgpu | tail -20
```

### "HSA_STATUS_ERROR_OUT_OF_RESOURCES"

```bash
# Sätt GFX version override
export HSA_OVERRIDE_GFX_VERSION=11.0.0
```

### Ollama använder inte GPU

```bash
# Kolla att ROCm hittas
ls /opt/rocm/

# Starta om Ollama efter ROCm-installation
sudo systemctl restart ollama

# Kolla Ollama logs
journalctl -u ollama -f
```

### Permission denied på /dev/kfd

```bash
# Lägg till användare i rätt grupper
sudo usermod -aG video,render $USER

# Logga ut och in igen!

# Verifiera
groups
# Bör innehålla: video render
```

## Installerade Paket (Referens)

Fullständig lista över ROCm-paket:

```
comgr                    3.0.0.60403-128~22.04
hipblas                  2.4.0.60403-128~22.04
hipfft                   1.0.18.60403-128~22.04
hipsolver                2.4.0.60403-128~22.04
hipsparse                3.2.0.60403-128~22.04
hipsparselt              0.2.3.60403-128~22.04
hsa-rocr                 1.15.0.60403-128~22.04
rccl                     2.22.3.60403-128~22.04
rocalution               3.2.3.60403-128~22.04
rocblas                  4.4.1.60403-128~22.04
rocfft                   1.0.32.60403-128~22.04
rocm-ml-sdk              6.4.3.60403-128~22.04
rocm-opencl              2.0.0.60403-128~22.04
rocm-smi-lib             7.7.0.60403-128~22.04
rocminfo                 1.0.0.60403-128~22.04
rocrand                  3.3.0.60403-128~22.04
rocsolver                3.28.2.60403-128~22.04
rocsparse                3.4.0.60403-128~22.04
```

## User Groups

Användaren måste vara medlem i:

```
video render ollama docker
```

Lägg till med:
```bash
sudo usermod -aG video,render,ollama,docker $USER
```

## Kernel Module

AMDGPU kernel module bör laddas automatiskt:

```bash
$ lsmod | grep amdgpu
amdgpu              19730432  17
```

Parametrar:
```bash
$ cat /sys/module/amdgpu/parameters/ppfeaturemask
0xfff7bfff
```

---

## Snabbinstallation (Copy-Paste)

```bash
#!/bin/bash
# ROCm 6.4.3 + Ollama Quick Install för Ubuntu 22.04 + AMD 7800 XT

set -e

# 1. Förbered
sudo apt update && sudo apt upgrade -y
sudo apt install -y wget gnupg2

# 2. ROCm repo
sudo mkdir -p /etc/apt/keyrings
wget https://repo.radeon.com/rocm/rocm.gpg.key -O - | \
    gpg --dearmor | sudo tee /etc/apt/keyrings/rocm.gpg > /dev/null
echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/amdgpu/6.4.3/ubuntu jammy main" | \
    sudo tee /etc/apt/sources.list.d/amdgpu.list
sudo apt update

# 3. ROCm packages
sudo apt install -y rocm-ml-sdk

# 4. Miljövariabler
echo 'export HSA_OVERRIDE_GFX_VERSION=11.0.0' | sudo tee /etc/profile.d/rocm.sh
echo 'export HIP_VISIBLE_DEVICES=0' | sudo tee -a /etc/profile.d/rocm.sh
source /etc/profile.d/rocm.sh

# 5. Ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo mkdir -p /etc/systemd/system/ollama.service.d
echo -e '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"' | \
    sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl enable ollama

# 6. User groups
sudo usermod -aG video,render,ollama $USER

echo "=== KLAR! Logga ut och in, kör sedan: ==="
echo "ollama pull qwen2.5-coder:7b"
echo "rocm-smi --showproductname"
```

---

*Dokumenterad från fungerande system 2026-01-15*
