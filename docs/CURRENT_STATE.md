# AgentFarm - Current State

> **Uppdaterad:** 2026-01-15
>
> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md)

## Aktiv Branch

```
Branch: feature/affiliate-ads
Status: Unified monetization (merged from feature/early-access)
```

## Senaste Commits

```
71b3d68 feat: Add TierManager for unified access control
944f43d feat: Merge early-access into affiliate-ads for unified monetization
1ae19ac feat: Add affiliate system and deployment infrastructure
```

## Nyligen Slutfört

### 2026-01-15: Unified Monetization

- [x] Mergat `feature/early-access` → `feature/affiliate-ads`
- [x] Skapat `TierManager` för unified access control
- [x] Löst merge-konflikter i `__init__.py` och `server.py`
- [x] Fixat RecursionGuard test (threshold 3 → 5)
- [x] Alla 111 tester passerar

### Unified Monetization Module

```
src/agentfarm/monetization/
├── __init__.py              # Exporterar allt
├── tiers.py                 # NY: TierManager (unified)
├── affiliates.py            # Hårdvaru-affiliates
├── stripe_integration.py    # Stripe betalningar
├── users.py                 # Användarprofiler
└── feedback.py              # Feedback-system
```

## Pågående TODO

### Prioritet 1: Säkerhet & Enterprise

- [ ] **Secure Vault** - Docker-volymer för företagsdata
  - `security/vault.py` - SecureVault class
  - `security/context_injector.py` - RAG med ChromaDB
  - Temporära volymer som rensas efter session
  - Early Access only

### Prioritet 2: Hardware & Monitoring

- [ ] **GPU Monitoring** - Real-time stats för hardware-sidan
  - `monitoring/gpu_monitor.py` - AMD ROCm stats (rocm-smi)
  - `monitoring/performance.py` - Tokens/sek tracking
  - Integration med LLM Router för latency-mätning
  - Live dashboard på /hardware

### Prioritet 3: Kompletteringar

- [ ] Fler affiliate-retailers (Proshop, Amazon/Adtraction)
- [ ] Streaming output i web UI
- [ ] Token usage dashboard per agent
- [ ] MCP server test med Claude Desktop
- [ ] Docker sandbox integration tests

## Arkitekturella Beslut

### Dual Revenue Model

```
Beslut: Två separata men integrerade intäktsströmmar
Motivering: Täcker både DIY-community och enterprise

Branch 1 (Affiliates):
- /hardware sida med GPU-rekommendationer
- Click tracking för svenska retailers
- Ingen inloggning krävs

Branch 2 (Early Access):
- Stripe-prenumeration
- Company context injection (Vault)
- VPN-access via WireGuard
```

### TierManager som Controller

```
Beslut: Central TierManager koordinerar alla monetization-komponenter
Motivering: Single source of truth för access control

TierManager
├── UserManager (profiler, tokens)
├── AffiliateManager (produkter, clicks)
└── StripeIntegration (betalningar)
```

### RecursionGuard Threshold

```
Beslut: Ökat threshold från 3 → 5 identiska calls
Motivering: Multi-step workflows triggade false positives
Fil: agents/base.py:RecursionGuard
```

## Kända Begränsningar

1. **Evaluation Suite** - 65% passerar (6/11 tester)
   - Bugfix-tester förväntar sig att filer finns
   - Behöver justering av test setup

2. **Gemini Rate Limit** - 15 RPM är väldigt strikt
   - Använd Ollama/Groq som primär

3. **Docker Sandbox** - Implementerad men otestad
   - Behöver integrationstester

## Nästa Session

När användaren säger "fortsätt":

1. Läs denna fil för kontext
2. Kolla git status för uncommitted changes
3. Fortsätt med TODO-listan ovan

## Kommandon för Snabbstart

```bash
# Kör tester
python -m pytest tests/ -v

# Starta web UI
agentfarm web --port 8080

# Verifiera imports
python -c "from agentfarm.monetization import TierManager; print('OK')"

# Git status
git log --oneline -5
git status
```

---

*Denna fil bör uppdateras vid varje session-slut.*
