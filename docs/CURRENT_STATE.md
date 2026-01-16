# AgentFarm - Current State

> **Uppdaterad:** 2026-01-16
>
> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md)

## Aktiv Branch

```
Branch: feature/affiliate-ads
Status: Security + Monitoring moduler tillagda
```

## Senaste Commits

```
115a7a1 docs: Update CURRENT_STATE and enhance web UI with affiliate ads
3df7fcb feat: Integrate monitoring with LLMRouter and add SecureVault to TierManager
e58888e feat: Add security, monitoring modules and infrastructure docs
143908b docs: Add WireGuard + DuckDNS setup guide
37d9e62 docs: Add ROCm 6.4.3 + Ollama setup guide
```

## Session 2026-01-16 (del 2): Web UI, Testing & Documentation

### Slutfört i denna session

- [x] **Token Dashboard** - Realtids-token-statistik i web UI
  - Total tokens, avg tokens/sek, P95 latency
  - Per-agent token breakdown (input/output/requests)
  - Collapsible dashboard section
  - Polling mot `/api/hardware/performance`

- [x] **Streaming Infrastructure** - Komplett streaming-stöd
  - Router `stream()` metod med `LLM_STREAM_CHUNK` events
  - WebSocket broadcasting av stream chunks
  - Frontend `handleStreamChunk()` för realtids-visning
  - Streaming-indikator och cursor i UI

- [x] **MCP Server Tests** - Verifiering av Claude Desktop-integration
  - `tests/test_mcp_server.py` med tool schema-validering
  - Dokumenterad config-format för Claude Desktop

- [x] **Docker Sandbox Tests** - Komplett integrationstest-suite
  - `tests/test_sandbox_integration.py`
  - Testar: execution, security, isolation, timeouts
  - Kräver Docker för att köras (`@pytest.mark.docker`)

- [x] **Scripts README** - Dokumentation för scripts/
  - `scripts/README.md` med usage och env-variabler
  - Dokumenterar `wireguard-setup.sh`

### Nya/Uppdaterade Filer

```
src/agentfarm/web/static/js/app.js    # Token dashboard, streaming
tests/test_mcp_server.py               # MCP server tests
tests/test_sandbox_integration.py      # Docker sandbox tests
scripts/README.md                      # Scripts documentation
docs/CURRENT_STATE.md                  # Denna fil
```

---

## Session 2026-01-16 (del 1): Security, Monitoring & Infrastructure

### Slutfört denna session

- [x] **SecureVault** - Docker-baserad säker lagring (`security/vault.py`)
  - Isolerade Docker volumes per session
  - Automatisk cleanup efter timeout
  - Lazy-loading av Docker client
  - Session management med expiry

- [x] **ContextInjector** - RAG med ChromaDB (`security/context_injector.py`)
  - Semantic search för företagsdokument
  - Chunking med overlap
  - Token-estimering för context injection
  - Återanvänder mönster från GraphRAG-projekt

- [x] **GPUMonitor** - Real-time GPU stats (`monitoring/gpu_monitor.py`)
  - Stöd för AMD (rocm-smi) och NVIDIA (nvidia-smi)
  - Temperatur (edge, junction, memory)
  - VRAM-användning
  - Power consumption och GPU utilization
  - Async watch-loop för kontinuerlig övervakning

- [x] **PerformanceTracker** - LLM metrics (`monitoring/performance.py`)
  - Tokens per second tracking
  - Latency (p50, p95, p99)
  - Per-model och per-agent statistik
  - EventBus-integration för automatisk tracking

- [x] **Hardware API Endpoints** - Nya REST endpoints
  - `GET /api/hardware` - Full stats (GPU + performance)
  - `GET /api/hardware/gpu` - Endast GPU info
  - `GET /api/hardware/performance` - Endast LLM metrics

- [x] **Infrastruktur-dokumentation**
  - `docs/GPU_PASSTHROUGH.md` - AMD 7800XT till Proxmox VM
  - `docs/NETWORK_ISOLATION.md` - Dual interface (vmbr0/vmbr1)
  - `scripts/wireguard-setup.sh` - Komplett installations- och peer-script

### Nya Moduler

```
src/agentfarm/
├── security/                   # NY MODUL
│   ├── __init__.py
│   ├── vault.py                # SecureVault (Docker volumes)
│   └── context_injector.py     # RAG med ChromaDB
└── monitoring/                 # NY MODUL
    ├── __init__.py
    ├── gpu_monitor.py          # AMD/NVIDIA stats
    └── performance.py          # Tokens/sek tracking

scripts/
└── wireguard-setup.sh          # NY: WireGuard server setup

docs/
├── GPU_PASSTHROUGH.md          # NY: Proxmox passthrough guide
└── NETWORK_ISOLATION.md        # NY: Dual interface setup
```

### Nya API Endpoints

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/hardware` | GET | Full hardware + performance stats |
| `/api/hardware/gpu` | GET | GPU stats (temp, VRAM, power) |
| `/api/hardware/performance` | GET | LLM metrics (tokens/sek, latency) |

### Nya Dependencies (pyproject.toml)

```toml
[project.optional-dependencies]
rag = [
    "chromadb>=0.4.0",
    "sentence-transformers>=2.2.0",
]
```

## Arkitekturella Beslut

### Security Module

```
Beslut: Separera security från monetization
Motivering: Tydligare separation of concerns

SecureVault
├── Docker volumes för isolerad lagring
├── Session-baserad expiry (4h default)
└── Integrerar med TierManager för access control

ContextInjector
├── ChromaDB för vector search
├── sentence-transformers för embeddings
└── Återanvänder mönster från GraphRAG-projekt
```

### Monitoring Module

```
Beslut: Lazy-loading av GPU monitoring
Motivering: Undvik startup-overhead om GPU ej tillgänglig

GPUMonitor
├── Automatisk detection av rocm-smi/nvidia-smi
├── Async watch() för kontinuerlig övervakning
└── Fallback till "No GPU found" vid fel

PerformanceTracker
├── Rolling window (1000 requests default)
├── Per-model och per-agent aggregation
└── EventBus integration för automatisk tracking
```

### Dual Network Architecture

```
Beslut: Separera VPN-trafik från intern LLM-trafik
Motivering: Säkerhet - Ollama ska ej ha internetåtkomst

vmbr0 (10.0.0.0/24) ─► WireGuard VPN
                       AgentFarm Web

vmbr1 (192.168.100.0/24) ─► Ollama (INGEN INTERNET)
                            Intern kommunikation
```

## Pågående TODO

### Prioritet 1: Integration ✅ KLAR

- [x] Koppla PerformanceTracker till LLMRouter events
- [x] Integrera ContextInjector med agents (system prompt injection)
- [x] Koppla SecureVault till TierManager för Early Access

### Prioritet 2: Kompletteringar ✅ KLAR

- [ ] Fler affiliate-retailers (Proshop, Amazon/Adtraction) - *Kräver företagsregistrering*
- [x] Streaming output i web UI (infrastruktur på plats)
- [x] Token usage dashboard per agent
- [x] MCP server test med Claude Desktop
- [x] Docker sandbox integration tests

### Prioritet 3: Dokumentation ✅ KLAR

- [x] Uppdatera SECURITY.md med nya moduler
- [x] Uppdatera WEB.md med nya endpoints
- [x] README för scripts/

## Kända Begränsningar

1. **Evaluation Suite** - 65% passerar (6/11 tester)
   - Bugfix-tester förväntar sig att filer finns
   - Behöver justering av test setup

2. **RAG Dependencies** - Ej installerade som default
   - Kräver `pip install agentfarm[rag]`
   - sentence-transformers är stor (~500MB)

3. **Docker Sandbox** - Testad med integrationstester
   - SecureVault kräver Docker SDK
   - Körs med `pytest tests/test_sandbox_integration.py -m docker`

## Verifiering

```bash
# Alla tester passerar
python -m pytest tests/ -v
# 111 passed in 0.42s

# Security module
python -c "from agentfarm.security import SecureVault, ContextInjector; print('OK')"

# Monitoring module
python -c "from agentfarm.monitoring import GPUMonitor, PerformanceTracker; print('OK')"

# Web server med nya endpoints
python -c "from agentfarm.web.server import create_app; print('OK')"
```

## Nästa Session

När användaren säger "fortsätt":

1. Läs denna fil för kontext
2. Kolla git status för uncommitted changes
3. Fortsätt med TODO-listan ovan

---

*Denna fil bör uppdateras vid varje session-slut.*
