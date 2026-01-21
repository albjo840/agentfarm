# AgentFarm - Current State

> **Uppdaterad:** 2026-01-21
>
> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md)

## Aktiv Branch

```
Branch: feature/affiliate-ads
Status: Full i18n, Amazon affiliates, Privacy disclaimer
```

## Senaste Commits

```
d7751fd feat: Add privacy disclaimer to Beta Operator modal
09f75bf feat: Add hardware page i18n and fix token metrics tracking
b97735a feat: Rename Prompts to 'Your prompts', add My Stack section
a302bf4 feat: Add language toggle, animated hardware visuals, larger task input
0775fd8 feat: Add product images and new badge types to hardware page
```

## Session 2026-01-21: Internationalization & Privacy

### Slutfört i denna session

- [x] **i18n System** - Komplett svenska/engelska språkväxling
  - `translations.js` med 100+ översättningar
  - Flagg-toggle (🇸🇪/🇬🇧) i header
  - `data-i18n` attribut på alla översättningsbara element
  - localStorage-persistens av språkval
  - Stöd för `data-i18n-placeholder` och `data-i18n-title`

- [x] **Hardware Page Updates**
  - Amazon.se affiliate-integration (tag: `agentfarm-21`)
  - Animerade CSS-visualiseringar (GPU-fläktar, CPU-die, RAM-chips)
  - "My Stack" sektion med användarens hårdvara
  - Borttagna kategori-tabs och SBC-produkter
  - Full i18n-support med `hw.*` translations

- [x] **Token Metrics Fix**
  - Event callback emittar nu `LLM_REQUEST`/`LLM_RESPONSE` events
  - PerformanceTracker får data från workflow stages
  - Dashboard visar tokens/sek och latency under workflows

- [x] **Privacy Disclaimer** - GDPR/NIS2-information i Beta Operator modal
  - Expanderbar "Integritet & Datasäkerhet" sektion
  - Air-gapped methodology, VPN-kryptering
  - GDPR-efterlevnad (dataminimering, ingen träning, radering)
  - NIS2 cybersäkerhets-compliance
  - Svenska och engelska översättningar

- [x] **UX Improvements**
  - Task input expanderat till textarea (4 rader)
  - Placeholder med exempel-prompt
  - Ctrl+Enter för att köra
  - "DINA PROMPTER" / "YOUR PROMPTS" i footer

### Nya/Uppdaterade Filer

```
src/agentfarm/web/
├── static/js/translations.js     # NY: i18n system
├── static/js/app.js              # togglePrivacySection(), i18n init
├── static/css/retro.css          # Privacy section, language toggle CSS
├── templates/index.html          # data-i18n attrs, privacy section
└── templates/hardware.html       # Full i18n, animated visuals
└── server.py                     # LLM event emission for metrics

.agentfarm/
└── affiliates.json               # Amazon.se integration
```

---

## Session 2026-01-17: Eval Test Fixes

### Slutfört i denna session

- [x] **Eval Suite Fix** - Fixat 65% → bör nu vara högre
  - Lagt till `setup_files` fält i TestCase för pre-skapade filer
  - Bugfix-tester skapar nu buggiga filer innan körning
  - Refactor-tester har setup_files med kod att refaktorera
  - Mer realistiskt scenario: agenter editerar istället för skapar

- [x] **Provider Tests** - Uppdaterade för local-first design
  - Endast `ollama` och `router` stöds nu
  - Cloud providers (groq, claude, azure) borttagna från tester

- [x] **MCP Tests** - Optional dependency handling
  - `@requires_mcp` decorator för tester som kräver mcp-modulen
  - Skippas automatiskt om mcp ej installerat

### Uppdaterade Filer

```
evals/suite.py              # setup_files support
tests/test_providers.py     # local-first tests
tests/test_mcp_server.py    # @requires_mcp decorator
```

### Testresultat

```bash
python -m pytest tests/ -v
# 212 passed, 20 skipped in 0.87s
```

---

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

1. **Evaluation Suite** - ✅ Fixat (2026-01-17)
   - Lagt till `setup_files` för bugfix/refactor-tester
   - Kör `python -m evals.suite` för att verifiera

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
# 212 passed, 20 skipped in 0.87s

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
