# AgentFarm Security Architecture

> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [MONETIZATION.md](./MONETIZATION.md)

## Översikt

AgentFarm är designat för att kunna hantera företagsdata säkert:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       SECURITY LAYERS                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Layer 1: Network Isolation                                            │
│  └── WireGuard VPN, isolerade nätverk                                  │
│                                                                         │
│  Layer 2: Access Control                                               │
│  └── TierManager, device fingerprint, Stripe verification              │
│                                                                         │
│  Layer 3: Data Isolation                                               │
│  └── Secure Vault, temporära Docker-volymer                            │
│                                                                         │
│  Layer 4: Execution Sandbox                                            │
│  └── Docker containers, resource limits                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 1. Network Isolation (TODO)

### Målarkitektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PROXMOX HOST                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    AGENT VM                                      │   │
│  │                                                                  │   │
│  │  ┌──────────────────┐        ┌──────────────────┐              │   │
│  │  │  Interface A     │        │  Interface B     │              │   │
│  │  │  (vmbr0)         │        │  (vmbr1)         │              │   │
│  │  │                  │        │                  │              │   │
│  │  │  WireGuard VPN   │        │  Internal Only   │              │   │
│  │  │  User ↔ API      │        │  LLM Traffic     │              │   │
│  │  │                  │        │  NO INTERNET     │              │   │
│  │  └────────┬─────────┘        └────────┬─────────┘              │   │
│  │           │                           │                         │   │
│  │           ▼                           ▼                         │   │
│  │  ┌──────────────────┐        ┌──────────────────┐              │   │
│  │  │  Web Server      │        │  Ollama          │              │   │
│  │  │  (aiohttp)       │        │  (LLM Inference) │              │   │
│  │  └──────────────────┘        └──────────────────┘              │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### WireGuard Setup

Befintlig implementation i `web/server.py`:

```python
# /api/wireguard/new-peer endpoint
async def api_wireguard_qr_handler(request):
    # 1. Generera nytt key pair
    # 2. Hitta nästa lediga IP (10.0.0.X)
    # 3. Lägg till peer i wg0.conf
    # 4. Returnera QR-kod för mobil
```

**Config:**
```bash
# /etc/wireguard/wg0.conf
[Interface]
PrivateKey = <server_private_key>
Address = 10.0.0.1/24
ListenPort = 51820

[Peer]
PublicKey = <client_public_key>
AllowedIPs = 10.0.0.2/32
```

## 2. Secure Vault (TODO)

### Målarkitektur

Temporär Docker-volym för företagsdata:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      SECURE VAULT                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Upload Flow:                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │  Client  │───►│  Upload  │───►│  Encrypt │───►│  Docker  │        │
│  │  (HTTPS) │    │  API     │    │  at Rest │    │  Volume  │        │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘        │
│                                                                         │
│  Access Flow:                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                         │
│  │  Agent   │───►│  Mount   │───►│  Read    │                         │
│  │  Process │    │  Volume  │    │  Context │                         │
│  └──────────┘    └──────────┘    └──────────┘                         │
│                                                                         │
│  Cleanup (efter session):                                              │
│  ┌──────────┐    ┌──────────┐                                         │
│  │  Delete  │───►│  Verify  │                                         │
│  │  Volume  │    │  Removed │                                         │
│  └──────────┘    └──────────┘                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Planerad Implementation

```python
# src/agentfarm/security/vault.py (TODO)

class SecureVault:
    """Manages temporary Docker volumes for company data."""

    async def create_vault(self, session_id: str) -> str:
        """Create isolated Docker volume."""
        volume_name = f"agentfarm_vault_{session_id}"
        # docker volume create ...
        return volume_name

    async def upload_file(self, session_id: str, file: bytes, filename: str):
        """Upload file to vault."""
        # Encrypt file
        # Store in volume
        pass

    async def get_context(self, session_id: str) -> str:
        """Read context.txt from vault."""
        # Mount volume read-only
        # Read context
        pass

    async def destroy_vault(self, session_id: str):
        """Remove vault and all data."""
        # docker volume rm ...
        # Verify deletion
        pass
```

### Data Drop (Vector DB)

Framtida implementation med ChromaDB/FAISS:

```python
# src/agentfarm/security/context_injector.py (TODO)

class ContextInjector:
    """RAG-baserad context injection från Vault."""

    def __init__(self, vault: SecureVault):
        self.vault = vault
        self.vector_db = None  # ChromaDB eller FAISS

    async def ingest_documents(self, session_id: str, files: list[Path]):
        """Chunka och indexera dokument."""
        pass

    async def query_context(self, query: str, k: int = 5) -> list[str]:
        """Hämta relevanta chunks."""
        pass
```

## 3. Access Control

### TierManager Integration

```python
from agentfarm.monetization import TierManager, AccessLevel

tier_mgr = TierManager(storage_dir=".agentfarm")

# Kolla access före workflow
async def check_access(device_id: str) -> tuple[bool, str]:
    access, limits = tier_mgr.get_user_tier(device_id)

    if access == AccessLevel.FREE:
        # Ingen Vault-access
        return False, "Vault requires Early Access subscription"

    return True, "Access granted"
```

### Device Fingerprint

Användare identifieras via device fingerprint (cookie-baserat):

```python
def _get_device_id(request: web.Request) -> str:
    device_id = request.cookies.get("device_id")
    if not device_id:
        device_id = str(uuid.uuid4())
    return device_id
```

## 4. Execution Sandbox

### Docker Sandbox (`tools/sandbox.py`)

```python
class SandboxRunner:
    """Kör kod i isolerad Docker container."""

    def __init__(self, config: SandboxConfig):
        self.config = config

    async def run(self, code: str, language: str) -> SandboxResult:
        """Kör kod i sandbox."""
        # 1. Skapa container med limits
        # 2. Kopiera kod
        # 3. Exekvera med timeout
        # 4. Samla output
        # 5. Förstör container
        pass
```

### SandboxConfig

```python
@dataclass
class SandboxConfig:
    image: str = "agentfarm/sandbox:latest"
    memory_limit: str = "512m"
    cpu_limit: float = 0.5
    timeout: int = 30
    network_disabled: bool = True
    read_only_root: bool = True
```

## 5. Stripe Webhook Security

Webhook-verifiering i `stripe_integration.py`:

```python
def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
    """Verifiera Stripe webhook signature."""
    # HMAC-SHA256 verification
    # Skyddar mot spoofade webhooks
```

## Säkerhetsprinciper

### Data Handling

1. **Minimal retention** - Data raderas efter session
2. **Encryption at rest** - Företagsdata krypteras
3. **No logging** - Kunddata loggas aldrig
4. **Isolation** - Varje session har egen volym

### Network Security

1. **VPN-only** - Betalande kunder via WireGuard
2. **No egress** - LLM-containern har ingen internet-access
3. **Rate limiting** - nginx rate limits
4. **TLS everywhere** - Certbot/Let's Encrypt

### Code Execution

1. **Sandboxed** - Docker containers
2. **Resource limits** - Memory, CPU, timeout
3. **No network** - Containers kan inte nå ut
4. **Ephemeral** - Containers förstörs efter körning

---

*Status: Delvis implementerat. Se [CURRENT_STATE.md](./CURRENT_STATE.md) för TODO.*
