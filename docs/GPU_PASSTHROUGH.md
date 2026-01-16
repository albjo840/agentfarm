# GPU Passthrough Guide - AMD 7800XT till Proxmox VM

> **Målkonfiguration:** AMD Radeon RX 7800 XT (gfx1101) passthrough till Ubuntu 22.04 VM
>
> Se även: [ROCM_SETUP.md](./ROCM_SETUP.md) | [SECURITY.md](./SECURITY.md)

## Förutsättningar

| Komponent | Krav |
|-----------|------|
| **CPU** | AMD/Intel med IOMMU-stöd (AMD-Vi / VT-d) |
| **Moderkort** | IOMMU aktiverat i BIOS |
| **GPU** | AMD Radeon RX 7800 XT (Navi 32) |
| **Proxmox** | 8.x rekommenderas |
| **VM** | Ubuntu 22.04 LTS |

## Steg 1: Aktivera IOMMU i BIOS

Beroende på moderkortstillverkare:

- **ASUS:** Advanced → AMD CBS → NBIO → IOMMU = Enabled
- **MSI:** OC → AMD CBS → NBIO → IOMMU = Enabled
- **Gigabyte:** Settings → AMD CBS → NBIO → IOMMU = Enabled
- **ASRock:** Advanced → AMD CBS → IOMMU = Enabled

## Steg 2: Konfigurera Proxmox Host

### 2.1 Aktivera IOMMU i GRUB

```bash
# Redigera GRUB config
nano /etc/default/grub

# Ändra GRUB_CMDLINE_LINUX_DEFAULT till:
# För AMD CPU:
GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt"

# För Intel CPU:
GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on iommu=pt"
```

Uppdatera GRUB:

```bash
update-grub
reboot
```

### 2.2 Verifiera IOMMU

```bash
# Ska visa IOMMU-grupper
dmesg | grep -e DMAR -e IOMMU

# Lista IOMMU-grupper
find /sys/kernel/iommu_groups/ -type l
```

### 2.3 Identifiera GPU PCI-adresser

```bash
# Hitta AMD GPU
lspci -nn | grep -i amd

# Förväntat output (exempel):
# 03:00.0 VGA compatible controller [0300]: AMD/ATI [1002:747e]
# 03:00.1 Audio device [0403]: AMD/ATI [1002:ab30]
```

Notera PCI ID:n (t.ex. `1002:747e` och `1002:ab30`).

### 2.4 Konfigurera vfio-pci

```bash
# Lägg till vfio-moduler
echo "vfio" >> /etc/modules
echo "vfio_iommu_type1" >> /etc/modules
echo "vfio_pci" >> /etc/modules

# Bind GPU till vfio-pci
echo "options vfio-pci ids=1002:747e,1002:ab30" > /etc/modprobe.d/vfio.conf

# Blacklista AMD-drivrutiner på host
echo "blacklist amdgpu" > /etc/modprobe.d/blacklist-amdgpu.conf
echo "blacklist radeon" >> /etc/modprobe.d/blacklist-amdgpu.conf
```

### 2.5 Uppdatera initramfs

```bash
update-initramfs -u -k all
reboot
```

### 2.6 Verifiera vfio-pci binding

```bash
# Ska visa vfio-pci som driver
lspci -nnk -s 03:00

# Förväntat:
# Kernel driver in use: vfio-pci
```

## Steg 3: Skapa VM i Proxmox

### 3.1 Skapa ny VM

Via Proxmox Web UI:
1. **General:** VM ID, Name (t.ex. "ollama-server")
2. **OS:** Ubuntu 22.04 ISO
3. **System:**
   - Machine: q35
   - BIOS: OVMF (UEFI)
   - EFI Storage: local-lvm
4. **Disks:** VirtIO Block, 100GB+
5. **CPU:** host, 8+ cores
6. **Memory:** 32GB+ (för 16GB VRAM GPU)
7. **Network:** VirtIO, bridge vmbr0

### 3.2 Lägg till GPU via Proxmox UI

1. Gå till VM → Hardware → Add → PCI Device
2. Välj AMD GPU (båda enheter om möjligt)
3. Aktivera:
   - All Functions: ✓
   - ROM-Bar: ✓
   - PCI-Express: ✓

Alternativt via kommandorad:

```bash
# Redigera VM config (ersätt 100 med ditt VM-ID)
nano /etc/pve/qemu-server/100.conf

# Lägg till:
hostpci0: 03:00,pcie=1,x-vga=1
```

### 3.3 Extra VM-konfiguration

```bash
# I /etc/pve/qemu-server/100.conf, lägg till:
cpu: host,hidden=1,flags=+pcid
args: -cpu host,kvm=off,hv_vendor_id=proxmox
```

## Steg 4: Installera Ubuntu och ROCm

### 4.1 Installera Ubuntu 22.04

Starta VM och installera Ubuntu som vanligt.

### 4.2 Verifiera GPU i VM

```bash
# Ska visa AMD GPU
lspci | grep -i vga

# Installera AMD-drivrutiner (se ROCM_SETUP.md för detaljer)
sudo usermod -aG video,render $USER
```

### 4.3 Installera ROCm

Följ [ROCM_SETUP.md](./ROCM_SETUP.md) för fullständig ROCm-installation.

Sammanfattning:

```bash
# Lägg till ROCm repo
sudo mkdir -p /etc/apt/keyrings
wget https://repo.radeon.com/rocm/rocm.gpg.key -O - | \
    gpg --dearmor | sudo tee /etc/apt/keyrings/rocm.gpg > /dev/null

echo "deb [arch=amd64,i386 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/amdgpu/6.4.3/ubuntu jammy main" | \
    sudo tee /etc/apt/sources.list.d/amdgpu.list

sudo apt update
sudo apt install -y rocm-ml-sdk

# Verifiera
rocm-smi --showproductname
```

## Steg 5: Installera Ollama

```bash
# Installera Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Starta Ollama
ollama serve &

# Testa med en modell
ollama run llama3.2
```

## Felsökning

### GPU syns inte i VM

```bash
# På host: verifiera vfio binding
lspci -nnk -s 03:00

# I VM: kolla dmesg
dmesg | grep -i amdgpu
```

### IOMMU-grupp innehåller andra enheter

Om GPU:n delar IOMMU-grupp med andra enheter behöver du använda ACS override patch eller passthrough alla enheter i gruppen.

```bash
# Kontrollera IOMMU-grupps
for d in /sys/kernel/iommu_groups/*/devices/*; do
    n=${d#*/iommu_groups/*}; n=${n%%/*}
    printf 'IOMMU Group %s ' "$n"
    lspci -nns "${d##*/}"
done
```

### ROCm hittar inte GPU

```bash
# Sätt miljövariabler
export HSA_OVERRIDE_GFX_VERSION=11.0.0
export HIP_VISIBLE_DEVICES=0

# Lägg till permanent
echo 'export HSA_OVERRIDE_GFX_VERSION=11.0.0' >> ~/.bashrc
echo 'export HIP_VISIBLE_DEVICES=0' >> ~/.bashrc
```

### VM startar inte efter GPU-tillägg

- Prova utan x-vga=1
- Kontrollera att UEFI/OVMF används
- Prova med pcie=0

## Prestandatips

### Hugepages

```bash
# På host: aktivera hugepages
echo "vm.nr_hugepages = 4096" >> /etc/sysctl.conf
sysctl -p

# I VM config:
hugepages: 1024
```

### CPU Pinning

```bash
# I VM config (för 8 vCPUs på cores 0-7):
cpu: host
cores: 8
numa: 1
cpuunits: 1024

# Bind till specifika cores
taskset: 0-7
```

## Säkerhet

- GPU passthrough ger VM direkt tillgång till hårdvaran
- VM:en kan potentiellt påverka host-systemet
- Använd alltid brandvägg och nätverksisolering
- Se [SECURITY.md](./SECURITY.md) för mer info

---

*Guide skapad 2026-01-16. Testad med Proxmox 8.1, AMD 7800XT, Ubuntu 22.04.*
