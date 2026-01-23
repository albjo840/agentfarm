# AgentFarm Agent System

> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [PROVIDERS.md](./PROVIDERS.md)

## Agent Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WORKFLOW PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌───────┐│
│  │ PLANNER │───►│   UX    │───►│EXECUTOR │───►│VERIFIER │───►│REVIEW ││
│  │         │    │(optional│    │         │    │         │    │       ││
│  │ TaskPlan│    │  UI)    │    │Code Gen │    │ Tests   │    │ Final ││
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └───────┘│
│       │              │              │              │              │     │
│       ▼              ▼              ▼              ▼              ▼     │
│  AgentResult   AgentResult    AgentResult   AgentResult    AgentResult │
│  (summary)     (summary)      (summary)     (summary)      (summary)   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Agent Classes

### BaseAgent (`agents/base.py`)

Alla agenter ärver från `BaseAgent`:

```python
class BaseAgent(ABC):
    name: str
    provider: LLMProvider
    memory: MemoryManager | None
    recursion_guard: RecursionGuard
    default_max_tool_calls: int = 15  # Subklasser kan överskriva

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        ...

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        ...

    async def run(self, context: AgentContext) -> AgentResult:
        ...

    # Proaktiv samarbete
    async def request_quick_review(code, question) -> str
    async def brainstorm(topic, with_agents) -> list[str]
    async def check_approach(approach) -> tuple[bool, str]
```

### AgentContext

Minimal kontext som skickas till varje agent:

```python
@dataclass
class AgentContext:
    task_summary: str           # Kort beskrivning av uppgiften
    relevant_files: list[str]   # Endast filer som behövs
    previous_step_output: str   # Sammanfattning från förra agenten
    constraints: dict           # Eventuella begränsningar
    working_dir: str           # Arbetskatalog
```

### AgentResult

Resultat från varje agent:

```python
@dataclass
class AgentResult:
    success: bool
    output: str                 # Full output
    summary_for_next_agent: str # Kort sammanfattning för nästa agent
    files_modified: list[str]   # Ändrade filer
    tokens_used: int
```

## Specifika Agenter

### 1. PlannerAgent (`agents/planner.py`)

**Syfte:** Bryter ner uppgiften i steg

```python
planner = PlannerAgent(provider)
result = await planner.run(context)
# result.output innehåller TaskPlan JSON
```

**Output format (TaskPlan):**
```json
{
  "steps": [
    {
      "id": 1,
      "description": "Create main.py",
      "dependencies": [],
      "agent": "executor"
    },
    {
      "id": 2,
      "description": "Add tests",
      "dependencies": [1],
      "agent": "executor"
    }
  ]
}
```

### 2. UXDesignerAgent (`agents/ux_designer.py`)

**Syfte:** UI/UX-design för frontend-uppgifter

**Aktiveras automatiskt** om task innehåller:
- ui, ux, frontend, component
- pygame, game, sprite, graphics
- button, form, modal, etc.

```python
ux = UXDesignerAgent(provider)

# Design component
design = await ux.design_component(context, "LoginForm", requirements)
# design.layout, design.colors, design.interactions

# Review UI
review = await ux.review_ui(context, requirements)
# review.issues, review.suggestions
```

### 3. ExecutorAgent (`agents/executor.py`)

**Syfte:** Genererar och editerar kod

**Tools:**
- `read_file` - Läs fil
- `write_file` - Skriv fil
- `edit_file` - Editera fil
- `list_files` - Lista filer
- `request_review` - Be om kodgranskning
- `consult_planner` - Fråga planner om approach
- `sanity_check` - Verifiera approach med verifier

```python
executor = ExecutorAgent(provider)
result = await executor.run(context)
# result.files_modified = ["src/main.py", "tests/test_main.py"]
```

### 4. VerifierAgent (`agents/verifier.py`)

**Syfte:** Kör tester och validerar kod

**Config:** `default_max_tool_calls = 40`

**Tools:**
- `check_syntax` - Validera Python syntax
- `check_imports` - Verifiera imports
- `run_tests` - Kör pytest (parameter: `pattern` för -k filter)
- `run_linter` - Kör ruff
- `run_typecheck` - Kör type checking
- `read_file` - Läs fil för inspektion

```python
verifier = VerifierAgent(provider)
result = await verifier.run(context)
# result.output innehåller VerificationResult
```

**Output format (VerificationResult):**
```json
{
  "tests_passed": true,
  "lint_passed": true,
  "type_check_passed": false,
  "coverage": 85.5,
  "issues": [
    {"file": "main.py", "line": 42, "message": "Missing type hint"}
  ]
}
```

### 5. ReviewerAgent (`agents/reviewer.py`)

**Syfte:** Kodgranskning

**Config:** `default_max_tool_calls = 35`

```python
reviewer = ReviewerAgent(provider)
result = await reviewer.run(context)
# result.output innehåller ReviewResult
```

**Output format (ReviewResult):**
```json
{
  "approved": true,
  "comments": [
    {"file": "main.py", "line": 10, "comment": "Consider using dataclass"}
  ],
  "suggestions": ["Add docstrings", "Consider error handling"]
}
```

## RecursionGuard (`agents/base.py`)

Förhindrar oändliga loopar:

```python
class RecursionGuard:
    max_depth: int = 10           # Max nesting depth
    max_total_calls: int = 100    # Max totala anrop
    identical_task_threshold: int = 5  # Max identiska tasks

    def enter(self, agent_name: str, task_summary: str) -> None:
        # Raises RecursionLimitError om limit nådd

    def exit(self, agent_name: str) -> None:
        ...
```

**Shared guard:** Orchestrator delar samma guard med alla agenter.

## Agent Collaboration (`agents/collaboration.py`)

### ProactiveCollaborator

Agenter kan samarbeta direkt utan orchestrator. **Orchestrator konfigurerar automatiskt ProactiveCollaborator** för alla agenter vid uppstart:

```python
from agentfarm.agents.collaboration import ProactiveCollaborator

# Orchestrator skapar och injectar automatiskt:
collaborator = ProactiveCollaborator(base_collaborator)
for agent in agents:
    agent.set_proactive_collaborator(collaborator)

# Peer review under kodgenerering
feedback = await collaborator.request_peer_review(
    from_agent="executor",
    code_snippet="def hello(): ...",
    question="Is this the right pattern?"
)

# Multi-agent brainstorm
responses = await collaborator.brainstorm_design(
    from_agent="executor",
    design_question="REST or GraphQL?",
    participants=["planner", "reviewer"]
)

# Sanity check innan stor ändring
approved, feedback = await collaborator.sanity_check(
    from_agent="executor",
    approach="Refactoring entire auth module"
)
```

### CollaborationType

```python
class CollaborationType(Enum):
    PEER_REVIEW = "peer_review"       # Snabb kodgranskning
    BRAINSTORM = "brainstorm"         # Multi-agent diskussion
    SANITY_CHECK = "sanity_check"     # Verifiering innan action
    KNOWLEDGE_SHARE = "knowledge_share"  # Envägs kontext-delning
```

## Memory System (`memory/`)

Agenter har tillgång till minne:

```python
from agentfarm.memory import MemoryManager, ShortTermMemory, LongTermMemory

memory = MemoryManager(
    short_term=ShortTermMemory(max_entries=100),
    long_term=LongTermMemory(storage_path=".agentfarm/memory.json"),
)

# BaseAgent methods
agent.remember("key", "value", long_term=True)
value = agent.recall("key")
results = agent.search_memory("pattern")
```

## Parallel Execution (`execution/parallel.py`)

Steg utan dependencies kan köras parallellt:

```python
from agentfarm.execution.parallel import DependencyAnalyzer, ParallelExecutor

# Analysera dependencies
analyzer = DependencyAnalyzer(steps)
groups = analyzer.get_parallel_groups()
# [[0], [1, 2, 3], [4, 5]]  - Steg 1,2,3 kan köras parallellt

# Kör parallellt
executor = ParallelExecutor(steps, execute_fn, max_concurrent=4)
results = await executor.execute_all()
```

## Prompts (`prompts/`)

Varje agent har dedikerad system prompt:

```
prompts/
├── orchestrator_prompt.py
├── planner_prompt.py
├── executor_prompt.py
├── verifier_prompt.py
├── reviewer_prompt.py
└── ux_designer_prompt.py
```

Prompten hämtas via `agent.system_prompt` property.

---

*Se även: [PROVIDERS.md](./PROVIDERS.md) för LLM-konfiguration*
