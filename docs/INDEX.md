# AgentFarm Documentation Index

> **Syfte**: Denna dokumentation hjälper Claude att snabbt förstå projektets struktur och sammanhang vid nya sessioner.

## Quick Start för Claude

När användaren säger "fortsätt" eller "get context", läs dessa filer i ordning:
1. `docs/INDEX.md` (denna fil) - Översikt
2. `docs/ARCHITECTURE.md` - Systemarkitektur
3. `docs/CURRENT_STATE.md` - Pågående arbete och branches

## Dokumentstruktur

| Fil | Innehåll |
|-----|----------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Systemarkitektur och dataflöde |
| [MONETIZATION.md](./MONETIZATION.md) | Dual-revenue modell (Affiliates + Stripe) |
| [PROVIDERS.md](./PROVIDERS.md) | LLM-providers och routing |
| [AGENTS.md](./AGENTS.md) | Agent-systemet och workflow |
| [SECURITY.md](./SECURITY.md) | Säkerhetsarkitektur (Vault, VPN, isolation) |
| [WEB.md](./WEB.md) | Web interface och API endpoints |
| [CURRENT_STATE.md](./CURRENT_STATE.md) | Pågående arbete och nästa steg |
| [ROCM_SETUP.md](./ROCM_SETUP.md) | ROCm 6.4.3 + Ollama installation (testad config) |

## Projekt-översikt

```
AgentFarm
├── Vad: Token-effektivt multi-agent system för koduppgifter
├── Workflow: PLAN → [UX DESIGN] → EXECUTE → VERIFY → REVIEW
├── Revenue: Affiliates (hårdvara) + Stripe (Early Access)
└── Hosting: Lokal GPU (AMD ROCm) via Proxmox + WireGuard VPN
```

## Nyckelkoncept

### Dual Revenue Model
```
┌─────────────────────────────────────────────────────────┐
│                      USERS                              │
├─────────────────────────────────────────────────────────┤
│  DIY Builders          │     Enterprise/Betalande      │
│  ─────────────────     │     ────────────────────      │
│  • Läser /hardware     │     • Stripe Early Access     │
│  • Klickar affiliates  │     • Company Context (Vault) │
│  • Bygger egen farm    │     • Unlimited workflows     │
│                        │     • VPN-access              │
│  Revenue: Affiliate    │     Revenue: Subscription     │
└─────────────────────────────────────────────────────────┘
```

### Tech Stack
- **Backend**: Python 3.10+, aiohttp, Pydantic
- **LLM**: Ollama (lokal), Groq/Gemini/SiliconFlow (free tier)
- **Frontend**: 80s Sci-Fi tema, WebSocket real-time
- **Infra**: Proxmox, Docker, WireGuard VPN, nginx

## Filstruktur (viktiga filer)

```
src/agentfarm/
├── orchestrator.py          # Huvudkoordinator
├── monetization/            # Se MONETIZATION.md
│   ├── tiers.py             # TierManager (unified)
│   ├── affiliates.py        # Hårdvaru-affiliates
│   ├── stripe_integration.py
│   └── users.py
├── providers/               # Se PROVIDERS.md
│   ├── base.py              # LLMProvider ABC
│   ├── router.py            # Multi-model routing
│   └── ollama.py            # Lokal inference
├── agents/                  # Se AGENTS.md
│   ├── base.py              # BaseAgent + RecursionGuard
│   └── collaboration.py     # ProactiveCollaborator
└── web/                     # Se WEB.md
    └── server.py            # aiohttp + WebSocket
```

## Senaste ändringar

Se [CURRENT_STATE.md](./CURRENT_STATE.md) för:
- Aktiva branches
- Pågående arbete
- TODO-lista
- Senaste commits

---

*Uppdaterad: 2026-01-15*
