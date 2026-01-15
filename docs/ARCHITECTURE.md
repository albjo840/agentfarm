# AgentFarm Arkitektur

> Se även: [INDEX.md](./INDEX.md) | [AGENTS.md](./AGENTS.md) | [PROVIDERS.md](./PROVIDERS.md)

## Systemöversikt

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AGENTFARM PLATFORM                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     Web Interface (80s Sci-Fi)                    │  │
│  │  /            - Dashboard med robot-visualisering                │  │
│  │  /mobile      - Mobil UI för VPN-access                          │  │
│  │  /hardware    - Hårdvarurekommendationer (affiliates)            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │ WebSocket                                │
│                              ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    TierManager (Unified Access)                   │  │
│  │  • check_workflow_access() - Rate limiting                       │  │
│  │  • get_company_context() - Secure context injection              │  │
│  │  • create_checkout() - Stripe betalningar                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      Orchestrator                                 │  │
│  │  Workflow: PLAN → [UX] → EXECUTE → VERIFY → REVIEW               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│          ┌───────────────────┼───────────────────┐                     │
│          ▼                   ▼                   ▼                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │  Planner    │    │  Executor   │    │  Verifier   │    ...          │
│  │   Agent     │    │   Agent     │    │   Agent     │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│          │                   │                   │                      │
│          └───────────────────┼───────────────────┘                     │
│                              ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    LLM Router / Multi-Provider                    │  │
│  │  Ollama (lokal) ──► Groq (free) ──► Gemini (free) ──► Claude     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Dataflöde

### 1. Användare startar workflow

```
User Request
    │
    ▼
┌─────────────────┐
│ TierManager     │──► Kolla access (free/early_access)
│                 │──► Hämta company_context (om finns)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ Orchestrator    │──► Skapa AgentContext med minimal info
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ PlannerAgent    │──► Skapa TaskPlan med steps
└─────────────────┘
    │
    ▼
[UXDesignerAgent] ──► (Endast om UI-task detekteras)
    │
    ▼
┌─────────────────┐
│ ExecutorAgent   │──► Generera/editera kod
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ VerifierAgent   │──► Kör tester, lint, typecheck
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ ReviewerAgent   │──► Kodgranskning
└─────────────────┘
    │
    ▼
WorkflowResult
```

### 2. Token-effektivitet

Varje agent får minimal kontext via `AgentContext`:

```python
@dataclass
class AgentContext:
    task_summary: str           # Kort beskrivning
    relevant_files: list[str]   # Endast relevanta filer
    previous_step_output: str   # Sammanfattning från förra agenten
    constraints: dict           # Begränsningar
```

Varje `AgentResult` innehåller `summary_for_next_agent` för handoff.

## Nyckelklasser

### Orchestrator (`orchestrator.py`)

```python
class Orchestrator:
    def __init__(self, provider, working_dir, use_multi_provider=False):
        ...

    async def run_workflow(self, task: str) -> WorkflowResult:
        # 1. PLAN phase
        # 2. UX DESIGN phase (conditional)
        # 3. EXECUTE phase (parallel möjligt)
        # 4. VERIFY phase
        # 5. REVIEW phase
        ...
```

### BaseAgent (`agents/base.py`)

```python
class BaseAgent(ABC):
    # RecursionGuard för att förhindra loopar
    recursion_guard: RecursionGuard

    # Memory för kontext över sessioner
    memory: MemoryManager

    # Proaktiv samarbete med andra agenter
    async def request_quick_review(code, question) -> str
    async def brainstorm(topic, with_agents) -> list[str]
    async def check_approach(approach) -> tuple[bool, str]
```

### TierManager (`monetization/tiers.py`)

```python
class TierManager:
    users: UserManager
    affiliates: AffiliateManager
    stripe: StripeIntegration

    def check_workflow_access(device_id) -> tuple[bool, str]
    def get_company_context(device_id) -> str | None
    async def create_checkout(device_id, product) -> str | None
```

## Event System

Alla komponenter kommunicerar via EventBus:

```python
from agentfarm.events import EventBus, Event, EventType

bus = EventBus()
bus.subscribe(EventType.WORKFLOW_START, handler)
await bus.emit(Event(type=EventType.AGENT_MESSAGE, ...))
```

Event types:
- `WORKFLOW_START/COMPLETE/ERROR`
- `STEP_START/COMPLETE/FAILED`
- `AGENT_MESSAGE/THINKING/TOOL_CALL`
- `CODE_GENERATED/MODIFIED`
- `LLM_REQUEST/RESPONSE`

## Infrastruktur

Se [SECURITY.md](./SECURITY.md) för detaljer om:
- Proxmox VM-setup
- WireGuard VPN
- Nätverksisolering
- Docker sandbox

---

*Se även: [MONETIZATION.md](./MONETIZATION.md) för revenue-modellen*
