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

    # Max tool calls (subklasser kan overrida)
    default_max_tool_calls: int = 10  # VerifierAgent: 25, ReviewerAgent: 20

    # Proaktiv samarbete med andra agenter
    async def request_quick_review(code, question) -> str
    async def brainstorm(topic, with_agents) -> list[str]
    async def check_approach(approach) -> tuple[bool, str]
```

### Tracking Module (`tracking/`)

```python
from agentfarm.tracking import (
    ProgressTracker,      # Viktad fasspårning
    CodeQualityScore,     # Kvalitetspoäng A-F
    SmartRetryManager,    # Felkategoriserad retry
    TestResultAggregator, # Flaky test-detektion
)

# Progress tracking med viktade faser
tracker = ProgressTracker()
await tracker.start_phase(WorkflowPhase.EXECUTE, total_steps=5)
print(f"Progress: {tracker.progress.total_percent}%")

# Kvalitetspoäng
quality = CodeQualityScore.from_verification_result(result)
print(f"Grade: {quality.grade.value}")  # A, B, C, D, F

# Smart retry
retry = SmartRetryManager()
result = await retry.execute_with_retry(operation)
```

### ParallelVerifier (`agents/parallel_verifier.py`)

Kör verifieringskontroller parallellt för snabbare resultat:

```python
from agentfarm.agents.parallel_verifier import ParallelVerifier

verifier = ParallelVerifier(code_tools=CodeTools("."))
result = await verifier.verify_files(files, run_tests=True, run_lint=True)
print(f"Speedup: {result.parallel_speedup:.1f}x")  # Typiskt 2-3x
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
