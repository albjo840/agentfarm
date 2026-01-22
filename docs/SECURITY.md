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

## 2. Secure Vault

> **Status:** Implementerad i `src/agentfarm/security/vault.py`

### Arkitektur

Temporär Docker-volym för företagsdata med automatisk cleanup:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      SECURE VAULT                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Session Creation (Early Access only):                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │  Client  │───►│  Tier    │───►│  Create  │───►│  Docker  │        │
│  │  Request │    │  Check   │    │  Session │    │  Volume  │        │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘        │
│                                                                         │
│  Document Storage:                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                         │
│  │  Upload  │───►│  Alpine  │───►│  /vault/ │                         │
│  │  Content │    │  Container│    │  Directory│                        │
│  └──────────┘    └──────────┘    └──────────┘                         │
│                                                                         │
│  Automatic Cleanup (session expiry = 4h):                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                         │
│  │  Expired │───►│  Stop    │───►│  Remove  │                         │
│  │  Session │    │  Container│    │  Volume  │                         │
│  └──────────┘    └──────────┘    └──────────┘                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation

```python
from agentfarm.security import SecureVault, VaultSession

# Initialize vault
vault = SecureVault(
    session_duration=timedelta(hours=4),
    cleanup_interval=300,  # 5 min cleanup cycle
)

# Create session (via TierManager for Early Access check)
session = await vault.create_session(device_id)
# -> Creates Docker volume: agentfarm_vault_<hash>

# Store document
await vault.store_document(session, "context.md", content)

# List documents
docs = await vault.list_documents(session)

# Retrieve document
content = await vault.retrieve_document(session, "context.md")

# Manual cleanup (automatic cleanup also runs)
await vault.destroy_session(session)
```

### TierManager Integration

```python
from agentfarm.monetization import TierManager

tier_mgr = TierManager(storage_dir=".agentfarm", enable_vault=True)

# Get vault session (Early Access only)
session = await tier_mgr.get_vault_session(device_id)
if session:
    # User has Early Access - vault available
    await tier_mgr.store_in_vault(device_id, "readme.md", content)
    docs = await tier_mgr.list_vault_documents(device_id)
else:
    # Free tier - no vault access
    pass

# Stats include vault info
stats = tier_mgr.get_stats()
# {"vault": {"available": True, "active_sessions": 3, ...}}
```

### VaultSession Properties

| Property | Type | Description |
|----------|------|-------------|
| `session_id` | str | Unique session identifier |
| `volume_name` | str | Docker volume name |
| `created_at` | datetime | Session start time |
| `expires_at` | datetime | Auto-cleanup time (4h default) |
| `is_expired` | bool | True if session should be cleaned |

## 3. Context Injector (RAG)

> **Status:** Implementerad i `src/agentfarm/security/context_injector.py`

### Arkitektur

RAG-baserad context injection med ChromaDB för semantisk sökning:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     CONTEXT INJECTOR                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Document Ingestion:                                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │  Upload  │───►│  Chunk   │───►│  Embed   │───►│ ChromaDB │        │
│  │  Doc     │    │  Text    │    │  Vectors │    │  Store   │        │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘        │
│                                                                         │
│  Query Flow:                                                           │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│  │  Agent   │───►│  Embed   │───►│  Search  │───►│  Inject  │        │
│  │  Task    │    │  Query   │    │  Top-K   │    │  Context │        │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation

```python
from agentfarm.security import ContextInjector

# Initialize (requires: pip install chromadb sentence-transformers)
injector = ContextInjector(
    storage_path=".agentfarm/context",
    embedding_model="all-MiniLM-L6-v2",
)

# Check availability
if injector.is_available:
    # Add documents (chunked automatically)
    chunks = await injector.add_document(
        filename="api_guide.md",
        content=api_docs,
        metadata={"type": "api"},
        chunk_size=1000,
        chunk_overlap=200,
    )

    # Add text snippets directly
    doc_id = await injector.add_text(
        text="Our API uses JSON-RPC 2.0",
        source="api_notes",
    )

    # Search for relevant context
    results = await injector.search(
        query="How do I format API responses?",
        n_results=5,
    )
    # -> [ContextResult(text=..., source=..., score=0.85, metadata=...)]

    # Get context for agent injection
    result = await injector.get_context_for_query(
        query="Add user authentication",
        max_tokens=2000,
    )
    print(result.context)  # Formatted context with sources
    print(result.token_estimate)  # ~1850 tokens
```

### Agent Integration

BaseAgent automatically injects company context via ContextInjector:

```python
from agentfarm.agents.base import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self, provider, context_injector=None):
        super().__init__(provider, context_injector=context_injector)

# When agent.run() is called:
# 1. Fetches relevant company context via RAG
# 2. Injects into agent's context window
# 3. Agent sees "# Company Context" section in prompt
```

### Dependencies

```bash
# Install RAG dependencies
pip install "agentfarm[rag]"

# Or manually:
pip install chromadb>=0.4.0 sentence-transformers>=2.2.0
```

## 4. Access Control

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

## 5. Execution Sandbox

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

## 6. Stripe Webhook Security

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
4. **TLS everywhere** - Certbot/Let's Encrypt (se [SSL_SETUP.md](./SSL_SETUP.md))

### SSL/TLS Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TLS TERMINATION                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  External Traffic:                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│  │   Internet   │───►│    nginx     │───►│  AgentFarm   │             │
│  │   (HTTPS)    │    │  SSL Term    │    │  :8080       │             │
│  └──────────────┘    └──────────────┘    └──────────────┘             │
│                                                                         │
│  Domains:                                                               │
│  • agentfarm.se (Loopia DNS → 31.208.228.229)                         │
│  • taborsen.duckdns.org (DuckDNS → 31.208.228.229)                    │
│                                                                         │
│  Certificates:                                                          │
│  • Let's Encrypt via Certbot (snap)                                    │
│  • Auto-renewal via systemd timer                                       │
│  • 90 days validity, renewed at 30 days                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Code Execution

1. **Sandboxed** - Docker containers
2. **Resource limits** - Memory, CPU, timeout
3. **No network** - Containers kan inte nå ut
4. **Ephemeral** - Containers förstörs efter körning

---

*Status: SecureVault, ContextInjector, TierManager implementerade. Se [CURRENT_STATE.md](./CURRENT_STATE.md) för aktuellt läge.*

*Senast uppdaterad: 2026-01-22*
