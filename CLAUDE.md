# CLAUDE.md - AgentFarm

This file provides guidance for Claude Code when working with this repository.

## Project Overview

AgentFarm is a token-efficient multi-agent orchestration system for code tasks. It implements a structured workflow: **PLAN → UX DESIGN (conditional) → EXECUTE → VERIFY → REVIEW → SUMMARY**.

### Key Design Principles

1. **Token Efficiency** - Each agent receives minimal, focused context
2. **Provider Abstraction** - Swap LLM providers without code changes
3. **Safe Execution** - All generated code runs in Docker sandbox
4. **MCP Integration** - Exposes tools via Model Context Protocol
5. **Free-First** - Groq free tier as default, no cost to get started

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Set up any of these free API keys:
export GROQ_API_KEY=your_key       # https://console.groq.com/keys
export GOOGLE_API_KEY=your_key     # https://aistudio.google.com/app/apikey
export SILICONFLOW_API_KEY=your_key # https://cloud.siliconflow.cn/

# Run a plan
agentfarm plan "Add a hello world function"

# Run full workflow
agentfarm workflow "Add unit tests for utils.py"

# Launch the 80s sci-fi web interface
agentfarm web
```

## Project Structure

```
agentfarm/
├── policies/
│   └── AGENTS.md              # Repository policy and guidelines
├── src/agentfarm/
│   ├── __init__.py
│   ├── orchestrator.py        # Main workflow coordinator
│   ├── config.py              # Configuration management
│   ├── cli.py                 # Command-line interface
│   ├── mcp_server.py          # MCP server for external integration
│   ├── agents/                # Specialized agents (one per file)
│   │   ├── base.py            # BaseAgent ABC with token optimization + memory + collaboration
│   │   ├── collaboration.py   # AgentCollaborator + ProactiveCollaborator
│   │   ├── orchestrator_agent.py  # OrchestratorAgent - LLM-driven coordinator
│   │   ├── planner.py         # PlannerAgent - task breakdown
│   │   ├── executor.py        # ExecutorAgent - code changes + collaboration tools
│   │   ├── verifier.py        # VerifierAgent - testing/validation + retry logic
│   │   ├── reviewer.py        # ReviewerAgent - code review
│   │   ├── ux_designer.py     # UXDesignerAgent - UI/UX design
│   │   └── parallel_verifier.py  # ParallelVerifier - concurrent verification checks
│   ├── execution/             # Parallel execution system
│   │   ├── __init__.py
│   │   └── parallel.py        # DependencyAnalyzer + ParallelExecutor
│   ├── memory/                # Agent memory system
│   │   ├── base.py            # MemoryManager and base classes
│   │   ├── short_term.py      # In-memory LRU cache
│   │   └── long_term.py       # Persistent JSON storage
│   ├── tracking/              # Progress, quality, and retry tracking
│   │   ├── __init__.py        # Module exports
│   │   ├── progress.py        # ProgressTracker, WorkflowProgress
│   │   ├── quality.py         # CodeQualityScore, QualityGrade
│   │   ├── retry.py           # SmartRetryManager, ErrorCategory
│   │   └── test_aggregator.py # TestResultAggregator, flaky test detection
│   ├── prompts/               # System prompts per agent
│   │   ├── orchestrator_prompt.py
│   │   ├── planner_prompt.py
│   │   ├── executor_prompt.py
│   │   ├── verifier_prompt.py
│   │   ├── reviewer_prompt.py
│   │   └── ux_designer_prompt.py
│   ├── events/                # Event bus system
│   │   ├── __init__.py
│   │   └── bus.py             # EventBus, Event, EventType, PriorityLevel
│   ├── providers/             # LLM provider implementations
│   │   ├── base.py            # LLMProvider ABC
│   │   ├── router.py          # LLMRouter - multi-model routing + load balancing
│   │   ├── groq.py            # Groq API (default, free tier)
│   │   ├── gemini.py          # Google Gemini (free tier, 15 RPM)
│   │   ├── siliconflow.py     # SiliconFlow/Qwen (free tier)
│   │   ├── claude.py          # Anthropic Claude
│   │   ├── azure.py           # Azure OpenAI
│   │   └── ollama.py          # Ollama (local, free)
│   ├── web/                   # 80s Sci-Fi Web Interface
│   │   ├── server.py          # aiohttp web server
│   │   ├── static/            # CSS, JS
│   │   └── templates/         # HTML templates
│   ├── tools/                 # Agent tools
│   │   ├── file_tools.py      # File read/write/edit/search
│   │   ├── code_tools.py      # pytest, ruff, typecheck
│   │   ├── git_tools.py       # Git operations
│   │   └── sandbox.py         # Docker sandbox execution
│   └── models/
│       └── schemas.py         # Pydantic models for all data
├── docker/
│   └── Dockerfile.sandbox     # Sandbox container image
├── evals/                     # Evaluation suite
│   ├── suite.py               # Full eval with 11 test cases
│   ├── quick_test.py          # Fast sanity checks
│   └── results/               # Saved eval reports (JSON)
├── tests/                     # pytest test suite (60 tests)
├── .env                       # API keys (not in git)
└── pyproject.toml             # Project configuration
```

## Development Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run linter
python -m ruff check src/

# Format code
python -m ruff format src/

# Run CLI (requires any API key: GROQ, GOOGLE, SILICONFLOW)
agentfarm plan "task description"
agentfarm workflow "task description"

# Run the 80s sci-fi web interface
agentfarm web                    # Default: http://127.0.0.1:8080
agentfarm web --port 3000        # Custom port

# Run evaluation suite
python -m evals.quick_test       # Fast sanity check (~5s)
python -m evals.suite --list     # List all tests
python -m evals.suite            # Run full eval (~8 min)
python -m evals.suite -c codegen # Run specific category

# Run MCP server
agentfarm mcp
```

## Architecture

### Orchestrator-Agent Architecture

The system uses an **LLM-driven OrchestratorAgent** that dynamically coordinates worker agents:

```
User Task
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OrchestratorAgent (LLM)                       │
│  Tools: call_planner, call_executor, call_verifier,             │
│         call_reviewer, call_ux_designer, store_memory,          │
│         recall_memory, get_workflow_state                        │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Planner │ │Executor │ │Verifier │ │Reviewer │ │UXDesign │
   │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
        │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼
    TaskPlan  ExecutionResult VerifyResult ReviewResult ComponentDesign
```

**Key difference from traditional orchestration:**
- The OrchestratorAgent is an LLM that decides dynamically which agents to call
- Can adapt strategy based on results (retry, adjust approach, etc.)
- Uses memory to track progress and learnings

**Fixed Workflow (Orchestrator class):**
The main `Orchestrator` class also supports UX Designer with automatic detection:
```
PLAN → [UX DESIGN] → EXECUTE → VERIFY → REVIEW → SUMMARY
           ↑
    Activated if task contains UI keywords:
    ui, ux, frontend, component, pygame, game, sprite, graphics, etc.
```

### Memory System

Agents have access to short-term and long-term memory:

```python
from agentfarm.memory import MemoryManager, ShortTermMemory, LongTermMemory

memory = MemoryManager(
    short_term=ShortTermMemory(max_entries=100),
    long_term=LongTermMemory(storage_path=".agentfarm/memory.json"),
)

# Store information
memory.store("api_pattern", "Use async/await for all I/O", long_term=True)

# Retrieve information
pattern = memory.retrieve("api_pattern")

# Search memory
results = memory.search("authentication")
```

**Memory types:**
- **ShortTermMemory**: In-memory, session-scoped, LRU eviction
- **LongTermMemory**: Persistent JSON storage, survives restarts

### Parallel Execution System

The orchestrator can execute independent steps in parallel using the `execution/parallel.py` module:

```python
from agentfarm.execution.parallel import DependencyAnalyzer, ParallelExecutor

# Analyze step dependencies
analyzer = DependencyAnalyzer(steps)
groups = analyzer.get_parallel_groups()  # [[0], [1, 2, 3], [4, 5]]

# Execute steps concurrently
executor = ParallelExecutor(
    steps=steps,
    execute_fn=my_execute_function,
    max_concurrent=4,  # Limit concurrent executions
)
results = await executor.execute_all()
```

**Key features:**
- **Topological sorting** for dependency analysis
- **asyncio.gather()** for concurrent execution
- **Event callbacks** for UI updates: `step_start`, `step_complete`, `parallel_group_start`
- **Failure handling** with optional `stop_on_failure`

### Proactive Agent Collaboration

Agents can collaborate directly without orchestrator prompting:

```python
from agentfarm.agents.collaboration import ProactiveCollaborator, CollaborationType

# Set up proactive collaboration
proactive = ProactiveCollaborator(base_collaborator)

# Executor requests peer review during code generation
feedback = await proactive.request_peer_review(
    from_agent="executor",
    code_snippet="def hello(): return 'world'",
    question="Is this the right pattern?"
)

# Multiple agents brainstorm a design decision
responses = await proactive.brainstorm_design(
    from_agent="executor",
    design_question="Should we use REST or GraphQL?",
    participants=["planner", "ux"]
)

# Sanity check before proceeding
approved, feedback = await proactive.sanity_check(
    from_agent="executor",
    approach="I'm going to refactor the entire auth module"
)
```

**Collaboration types:**
- `PEER_REVIEW` - Quick code review during execution
- `BRAINSTORM` - Multi-agent design discussion
- `SANITY_CHECK` - Verify approach before proceeding
- `KNOWLEDGE_SHARE` - One-way context sharing

**BaseAgent collaboration methods:**
- `request_quick_review(code, question)` - Ask reviewer for feedback
- `brainstorm(topic, with_agents)` - Multi-agent discussion
- `check_approach(approach)` - Sanity check with verifier
- `share_knowledge(to_agent, knowledge, topic)` - Share context

### Event Bus System

The system uses an async pub/sub event bus for decoupled communication:

```python
from agentfarm.events import EventBus, Event, EventType, PriorityLevel

bus = EventBus()

# Subscribe to events
async def on_code_generated(event: Event):
    print(f"Code from {event.source}: {event.data['code']}")

bus.subscribe(EventType.CODE_GENERATED, on_code_generated)

# Emit events
await bus.emit(Event(
    type=EventType.CODE_GENERATED,
    source="executor",
    data={"code": "def hello(): pass", "file_path": "main.py"},
))

# Start event loop (background processing)
asyncio.create_task(bus.run())
```

**Event Types:**
- `WORKFLOW_START/COMPLETE/ERROR` - Workflow lifecycle
- `STEP_START/COMPLETE/FAILED` - Step execution
- `AGENT_MESSAGE/THINKING/TOOL_CALL` - Agent activity
- `CODE_GENERATED/MODIFIED` - Code changes
- `LLM_REQUEST/RESPONSE/STREAM_CHUNK` - LLM routing
- `INTERRUPT` - Critical priority, interrupts processing

**Priority Levels:** `LOW`, `NORMAL`, `HIGH`, `CRITICAL`

### LLM Router (Multi-Model)

Routes requests to optimal local Ollama models based on task type:

```python
from agentfarm.providers.router import LLMRouter, TaskType

router = LLMRouter(ollama_base_url="http://localhost:11434")
await router.initialize()  # Check model availability

# Route code generation to best model
response, model_used = await router.complete(
    messages=[{"role": "user", "content": "Write a function..."}],
    task_type=TaskType.CODE_GENERATION,
)
print(f"Used: {model_used}")  # e.g., "qwen-coder"
```

**Supported Models:**
| Model | Best For | Priority |
|-------|----------|----------|
| qwen2.5-coder:7b | Code generation, review | 9 |
| qwen3:14b | Complex reasoning, planning | 8 |
| phi4 | Code + math | 7 |
| gemma2:9b | Verification, general | 6 |
| mistral-nemo | Swedish, planning | 6 |
| nemotron-mini | Fast simple responses | 5 |

**Task Types:** `CODE_GENERATION`, `CODE_REVIEW`, `PLANNING`, `REASONING`, `VERIFICATION`, `MATH`, `GENERAL`

### Web Interface Features

The 80s sci-fi web interface includes:

**Robot Visualizer (`robots.js`):**
- Pixel art robots for each agent
- Walking animations when robots communicate
- Speech bubbles showing messages
- Idle behavior: wandering, thinking, scanning
- Collaboration visualization: robots gravitate toward each other

**WebSocket Events:**
| Event | Data | Description |
|-------|------|-------------|
| `workflow_start` | `{task, provider}` | Workflow begins |
| `agent_message` | `{agent, content}` | Agent sends message |
| `parallel_execution_start` | `{total_steps, groups}` | Parallel execution begins |
| `step_start/complete` | `{step_id, success}` | Step lifecycle |
| `agent_collaboration` | `{initiator, participants, type, topic}` | Proactive collaboration |
| `workflow_complete` | `{success, error}` | Workflow ends |
| `LLM_REQUEST/RESPONSE` | `{model, task_type, latency_ms}` | Router events |

**REST API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/providers` | GET | List available LLM providers |
| `/api/events` | GET | Event bus metrics + history |
| `/api/events?type=LLM_REQUEST` | GET | Filter events by type |
| `/api/interrupt` | POST | Send interrupt `{"reason": "..."}` |
| `/api/router` | GET | LLM router status + model health |
| `/api/router/test` | POST | Test model `{"prompt": "...", "task_type": "code_generation"}` |

**Mobile Access:**
- Dashboard: `http://<server>:8080/`
- Mobile UI: `http://<server>:8080/mobile` or `/m`
- VPN access: `http://10.0.0.1:8080/mobile`

### Token Efficiency Strategy

1. **AgentContext** - Minimal context passed to each agent:
   - `task_summary` - Brief task description
   - `relevant_files` - Only files needed for this step
   - `previous_step_output` - Summary from last agent (not full output)
   - `constraints` - Any limitations

2. **summary_for_next_agent** - Each AgentResult includes a concise summary for handoff

3. **Tool filtering** - Each agent only has access to its specific tools

### Provider System

All providers with free tiers:

```python
# Groq (default, fast, free tier: 100k tokens/day)
from agentfarm.providers.groq import GroqProvider
provider = GroqProvider(model="llama-3.3-70b-versatile")

# Gemini (Google, free tier: 15 RPM, 1M tokens/min)
from agentfarm.providers.gemini import GeminiProvider
provider = GeminiProvider(model="gemini-1.5-flash-latest")

# SiliconFlow/Qwen (free tier for Qwen models)
from agentfarm.providers.siliconflow import SiliconFlowProvider
provider = SiliconFlowProvider(model="Qwen/Qwen2.5-7B-Instruct")

# Ollama (local, completely free)
from agentfarm.providers.ollama import OllamaProvider
provider = OllamaProvider(model="llama3.2")

# Claude (paid, high quality)
from agentfarm.providers.claude import ClaudeProvider
provider = ClaudeProvider(model="claude-sonnet-4-20250514")

# Auto-detect from environment:
from agentfarm.providers import get_provider
provider = get_provider()  # Finds first available API key
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | - | Groq API key (console.groq.com) |
| `GOOGLE_API_KEY` | - | Gemini API key (aistudio.google.com) |
| `GEMINI_API_KEY` | - | Alias for GOOGLE_API_KEY |
| `SILICONFLOW_API_KEY` | - | SiliconFlow key (cloud.siliconflow.cn) |
| `ANTHROPIC_API_KEY` | - | Claude API key |
| `OLLAMA_HOST` | localhost:11434 | Ollama server URL |
| `AGENTFARM_PROVIDER` | auto | Override: groq, gemini, qwen, claude, ollama |
| `AGENTFARM_MODEL` | provider-specific | Override model name |

## Key Files to Understand

| File | Purpose |
|------|---------|
| `agents/orchestrator_agent.py` | LLM-driven coordinator that dynamically calls other agents |
| `agents/base.py` | BaseAgent class with token optimization, memory, and proactive collaboration |
| `agents/collaboration.py` | AgentCollaborator + ProactiveCollaborator for agent-to-agent communication |
| `agents/executor.py` | ExecutorAgent with request_review, consult_planner, sanity_check tools |
| `agents/verifier.py` | VerifierAgent with retry logic and improved JSON fallback |
| `agents/parallel_verifier.py` | ParallelVerifier for concurrent syntax/test/lint/typecheck |
| `execution/parallel.py` | DependencyAnalyzer and ParallelExecutor for concurrent step execution |
| `memory/base.py` | MemoryManager for short/long-term memory |
| `tracking/progress.py` | ProgressTracker with weighted phases for workflow progress |
| `tracking/quality.py` | CodeQualityScore with letter grades (A-F) |
| `tracking/retry.py` | SmartRetryManager with error categorization |
| `tracking/test_aggregator.py` | TestResultAggregator for flaky test detection |
| `prompts/*.py` | Dedicated system prompts for each agent |
| `providers/base.py` | LLMProvider ABC for provider abstraction |
| `models/schemas.py` | All Pydantic models (TaskPlan, ExecutionResult, etc.) |
| `web/static/js/robots.js` | RobotVisualizer with idle behavior and collaboration animations |
| `web/server.py` | WebSocket server with collaboration event broadcasting |

## Code Patterns

### Adding a New Agent

```python
# src/agentfarm/agents/my_agent.py
from agentfarm.agents.base import BaseAgent, AgentContext, AgentResult
from agentfarm.memory.base import MemoryManager

class MyAgent(BaseAgent):
    name = "MyAgent"

    def __init__(self, provider, memory: MemoryManager | None = None):
        super().__init__(provider, memory)
        # Register agent-specific tools
        self._register_my_tools()

    @property
    def system_prompt(self) -> str:
        # Load from prompts module for easier editing
        try:
            from agentfarm.prompts import my_agent_prompt
            return my_agent_prompt.SYSTEM_PROMPT
        except ImportError:
            return "Your minimal, focused system prompt"

    def get_tools(self) -> list[ToolDefinition]:
        return self._tools  # Only tools this agent needs

    async def process_response(self, response, tool_outputs) -> AgentResult:
        # Use memory to store learnings
        if self.memory:
            self.remember("last_output", response.content[:200])

        return AgentResult(
            success=True,
            output=response.content,
            summary_for_next_agent="Concise summary for next agent",
        )
```

### Adding a New Provider

```python
# src/agentfarm/providers/my_provider.py
from agentfarm.providers.base import LLMProvider, CompletionResponse

class MyProvider(LLMProvider):
    async def complete(self, messages, tools=None, **kwargs) -> CompletionResponse:
        # Call your LLM API
        return CompletionResponse(content="...", input_tokens=X, output_tokens=Y)

    async def stream(self, messages, **kwargs):
        # Yield tokens
        yield "token"
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_schemas.py -v

# Run with coverage (requires pytest-cov)
python -m pytest tests/ --cov=agentfarm
```

Test files:
- `test_schemas.py` - Pydantic model tests
- `test_providers.py` - Provider abstraction tests
- `test_agents.py` - Agent context/result tests
- `test_tools.py` - File tools tests (requires aiofiles)

## Policy Compliance

All changes must follow `policies/AGENTS.md`:
- Use the PLAN→[UX DESIGN]→EXECUTE→VERIFY→REVIEW workflow
- Type hints required on all functions
- Async/await for I/O operations
- Pydantic for data models
- Maximum 200 lines per logical change

## Common Tasks

### Run a workflow programmatically

```python
import asyncio
from agentfarm import Orchestrator
from agentfarm.providers.groq import GroqProvider

async def main():
    provider = GroqProvider(model="llama-3.3-70b-versatile")
    orchestrator = Orchestrator(provider, working_dir="./my_project")

    result = await orchestrator.run_workflow(
        task="Add unit tests for utils.py",
        context_files=["src/utils.py"],
    )

    print(result.pr_summary)
    print(f"Tokens used: {result.total_tokens_used}")

asyncio.run(main())
```

### Use as MCP server

Add to Claude Desktop config (`~/.config/claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "agentfarm": {
      "command": "agentfarm",
      "args": ["mcp"],
      "cwd": "/path/to/your/project",
      "env": {
        "GROQ_API_KEY": "your_key_here"
      }
    }
  }
}
```

## Dependencies

Core (always installed):
- `pydantic` - Data validation
- `httpx` - Async HTTP client
- `aiofiles` - Async file operations

Optional:
- `mcp` - MCP server support
- `docker` - Sandbox execution
- `gitpython` - Git operations
- `anthropic` - Claude provider
- `groq` - Groq provider (SDK, optional - httpx used by default)

Dev:
- `pytest`, `pytest-asyncio` - Testing
- `ruff` - Linting/formatting

## Evaluation Suite

The `evals/` directory contains a comprehensive evaluation suite for testing agent capabilities.

### Structure

```
evals/
├── __init__.py
├── suite.py          # Full evaluation suite with 11 test cases
├── quick_test.py     # Fast sanity checks (~5 seconds)
├── cases/            # (for future test case files)
└── results/          # Saved evaluation reports (JSON)
```

### Usage

```bash
# Quick sanity check - tests components without LLM calls
python -m evals.quick_test

# List all evaluation tests
python -m evals.suite --list

# Run full evaluation (requires Ollama or API keys)
python -m evals.suite

# Run specific category
python -m evals.suite --category codegen
python -m evals.suite --category bugfix
python -m evals.suite --category refactor
python -m evals.suite --category multistep
```

### Test Categories

| Category | Tests | Description |
|----------|-------|-------------|
| `codegen` | 4 | Create new code (functions, classes, APIs) |
| `bugfix` | 3 | Fix bugs in provided code snippets |
| `refactor` | 2 | Refactor code (extract methods, polymorphism) |
| `multistep` | 2 | Complex multi-file projects |

### Test Cases (11 total, 210 points)

| ID | Name | Category | Points |
|----|------|----------|--------|
| codegen-001 | Simple Function (is_prime) | codegen | 10 |
| codegen-002 | Calculator Class | codegen | 15 |
| codegen-003 | REST API Endpoint | codegen | 20 |
| codegen-004 | Data Processing Pipeline | codegen | 20 |
| bugfix-001 | Fix Off-by-One Error | bugfix | 10 |
| bugfix-002 | Fix Race Condition | bugfix | 15 |
| bugfix-003 | Fix SQL Injection | bugfix | 15 |
| refactor-001 | Extract Method | refactor | 20 |
| refactor-002 | Replace Conditionals with Polymorphism | refactor | 20 |
| multistep-001 | CLI Todo App | multistep | 30 |
| multistep-002 | Web Scraper with Tests | multistep | 35 |

### Validators

Each test uses validators to check results:
- `file_exists` - Check if file was created
- `file_contains` - Regex pattern match in file
- `python_syntax` - Valid Python syntax
- `function_exists` - Function defined in file
- `class_exists` - Class defined in file
- `tests_pass` - pytest passes

### Baseline Results (2026-01-13)

**Configuration:** Ollama local models (qwen2.5-coder:7b, llama3.2)

```
============================================================
  RESULTS SUMMARY
============================================================
  Passed: 6/11
  Score:  137.8/210 (65.6%)
  Time:   459.4s (7.6 minutes)

  By Category:
    codegen:   2/4 (50%)
    bugfix:    1/3 (33%)
    refactor:  1/2 (68%)
    multistep: 2/2 (94%)  ⭐ Best performance
============================================================
```

**Key Insights:**
- **Multistep tasks perform best** (94%) - agents excel at complex multi-file projects
- **Bugfix tests need adjustment** - agents expect files to exist for editing
- **Local LLMs work well** - Ollama models sufficient for most code generation

### Adding New Tests

```python
# In evals/suite.py
TestCase(
    id="codegen-005",
    name="My New Test",
    category=CATEGORY_CODEGEN,
    prompt="Create a function that...",
    validators=[
        {"type": "file_exists", "filename": "my_file.py"},
        {"type": "function_exists", "filename": "my_file.py", "function_name": "my_func"},
    ],
    difficulty="medium",
    points=15,
)
```

### Tracking System

The `tracking/` module provides progress tracking, quality metrics, and retry logic:

#### ProgressTracker

```python
from agentfarm.tracking import ProgressTracker, WorkflowPhase

tracker = ProgressTracker(event_callback=my_callback)

# Track workflow progress
await tracker.start_workflow("Add feature X")
await tracker.start_phase(WorkflowPhase.PLAN, total_steps=1)
await tracker.complete_phase(WorkflowPhase.PLAN)

await tracker.start_phase(WorkflowPhase.EXECUTE, total_steps=5)
for i in range(5):
    await tracker.update_step(WorkflowPhase.EXECUTE, i + 1)
await tracker.complete_phase(WorkflowPhase.EXECUTE)

print(f"Progress: {tracker.progress.total_percent}%")  # Weighted by phase
```

**Phase weights (default):** plan=10%, ux_design=5%, execute=50%, verify=15%, review=15%, summary=5%

#### CodeQualityScore

```python
from agentfarm.tracking import CodeQualityScore

quality = CodeQualityScore()

# Add metrics from verification
quality.add_test_results(passed=19, failed=1, skipped=2)
quality.add_lint_results(issues=["file.py:10: unused import"])
quality.add_type_results(errors=[])
quality.add_coverage(85.5)

print(f"Quality: {quality.grade.value} ({quality.total_score:.1f})")  # B (82.5)
print(quality.get_issues())  # Lists metrics below 70
```

**Grades:** A (90+), B (80+), C (70+), D (60+), F (<60)

#### SmartRetryManager

```python
from agentfarm.tracking import SmartRetryManager, ErrorCategory

retry_manager = SmartRetryManager()

async def flaky_operation():
    # ... operation that might fail
    pass

result = await retry_manager.execute_with_retry(
    operation=flaky_operation,
    categorize_error=lambda e: (
        ErrorCategory.TRANSIENT if "timeout" in str(e)
        else ErrorCategory.PERMANENT
    ),
)

if result.success:
    print(f"Succeeded after {result.attempts} attempts")
```

**Error categories:**
- `TRANSIENT`: Timeout, rate limit, network - 3 retries, exponential backoff
- `FLAKY`: Intermittent failures - 2 retries with jitter
- `FIXABLE`: Can be fixed by adjusting approach - 1 retry
- `PERMANENT`: Logic error, invalid input - no retry

#### TestResultAggregator

```python
from agentfarm.tracking import TestResultAggregator

aggregator = TestResultAggregator(storage_path=".agentfarm/test_history.json")

# Record test runs
aggregator.start_run()
aggregator.record_run("test_login", passed=True)
aggregator.record_run("test_checkout", passed=False, error="Timeout")
aggregator.end_run()

# Analyze patterns
flaky_tests = aggregator.get_flaky_tests()  # 20-80% pass rate
failing_tests = aggregator.get_consistently_failing_tests()

print(aggregator.get_report())
```

### Parallel Verification

`ParallelVerifier` runs verification checks concurrently for faster results:

```python
from agentfarm.agents.parallel_verifier import ParallelVerifier
from agentfarm.tools.code_tools import CodeTools

verifier = ParallelVerifier(code_tools=CodeTools("."))

result = await verifier.verify_files(
    files=["main.py", "utils.py"],
    run_tests=True,
    run_lint=True,
    run_typecheck=True,
)

print(f"Success: {result.success}")
print(f"Speedup: {result.parallel_speedup:.1f}x")
print(f"Failed checks: {[c.check_type for c in result.failed_checks]}")
```

**Parallel execution model:**
```
Sequential: |--syntax--|--imports--|--tests--|--lint--|--typecheck--|
Parallel:   |--syntax--| + |--tests--| + |--lint--| + |--typecheck--|
            |--imports--|
```

Typical speedup: 2-3x on multi-core systems.

### Overlapping Workflow Phases

The orchestrator supports overlapping execution and verification:

```python
from agentfarm import Orchestrator

orchestrator = Orchestrator(working_dir="./my_project")

# Standard workflow (sequential)
result = await orchestrator.run_workflow("Add feature X")

# Overlapping workflow (starts verify when 80% of execute is done)
result = await orchestrator.run_workflow_with_overlapping_phases(
    task="Add feature X",
    early_verify_threshold=0.8,  # Start verify at 80% execute
)
```

## Changelog

### 2026-01-24: Eval Regression Fix (76.2% score)

#### Problem
Eval score hade sjunkit till 51.4%. Bugfix, refactor och multistep kategorier failade.

#### Root Causes
1. **Pydantic validation errors** - `ReviewComment.severity` och `VerificationResult.lint_issues` fick `null` från LLM
2. **LLM path hallucination** - Agenter försökte läsa `/home/user/...`, `~/...`, `/tmp/...`
3. **Tool call loops** - Verifier/Reviewer slösade alla tool calls på icke-existerande filer

#### Fixes Implemented

**1. Null-value handling** (`agents/verifier.py`, `agents/reviewer.py`):
```python
# BEFORE (crash on null):
severity=c.get("severity", "info")  # Returns None if key exists but is null

# AFTER (handles null):
severity=c.get("severity") or "info"  # Falls back to "info" on None
lint_issues = data.get("lint_issues") or []
```

**2. Failed path tracking** - Stop LLM loops:
```python
self._failed_paths: set[str] = set()

async def _read_file(self, path: str) -> str:
    if path in self._failed_paths:
        return f"ERROR: Already tried '{path}' - skip this file."
```

**3. Show available files** - Help LLM find correct paths:
```python
if not file_path.exists():
    available = [f.name for f in self._working_dir.iterdir()][:10]
    return f"ERROR: File not found: {path}. Available files: {available}"
```

**4. Path validation** - Reject hallucinated absolute paths:
```python
try:
    file_path.resolve().relative_to(self._working_dir)
except ValueError:
    return f"ERROR: Path outside working directory. Use relative paths."
```

**5. Prompt improvements** - Added PATH RULES to system prompts:
```
## PATH RULES (CRITICAL):
- Use ONLY relative paths like "main.py", "src/utils.py"
- NEVER use absolute paths like /home/... or /tmp/...
- If a file doesn't exist after 2 attempts, skip it
```

#### Evaluation Results
| Category | Before | After | Change |
|----------|--------|-------|--------|
| codegen | 69.2% | 70% | +1% |
| bugfix | 75% | 81% | +6% |
| refactor | 24.4% | 60% | **+36%** |
| multistep | 94% | 95% | +1% |
| **Total** | **51.4%** | **76.2%** | **+25%** |

**Tests passed: 7/11** (was 6/11)

#### Files Modified
| File | Changes |
|------|---------|
| `agents/verifier.py` | Null handling, failed path tracking, path validation, prompt rules |
| `agents/reviewer.py` | Null handling, failed path tracking, path validation, prompt rules |
| `orchestrator.py` | stop_on_failure=True, file existence verification |
| `providers/ollama.py` | JSON fence pattern for tool calls |
| `agents/base.py` | MD5 hash for RecursionGuard |
| `tools/file_tools.py` | Fixed fuzzy matching regex order |
| `evals/suite.py` | --test flag now prints results |

---

### 2026-01-24: VerifierAgent Working Directory Fix

#### Bug Fix
- **VerifierAgent working_dir support** (`agents/verifier.py`):
  - Added `working_dir` parameter to constructor
  - `_check_syntax`, `_check_imports`, `_read_file` now resolve paths against working_dir
  - Fixed: Files created in temp directories were not found by verifier

- **Orchestrator updates** (`orchestrator.py`):
  - Now passes `working_dir` to VerifierAgent on initialization
  - Injects `read_file` from FileTools to verifier

- **Eval prompt improvements** (`evals/suite.py`):
  - Added explicit filenames to codegen prompts
  - Example: "VIKTIGT: Filen MÅSTE heta exakt 'prime.py'"

#### Evaluation Results
| Category | Before Fix | After Fix |
|----------|------------|-----------|
| codegen | 0/4 (0%) | 3/4 (81.5%) |

#### Files Modified
| File | Changes |
|------|---------|
| `agents/verifier.py` | working_dir parameter, path resolution in tools |
| `orchestrator.py` | Pass working_dir to VerifierAgent |
| `evals/suite.py` | Explicit filenames in prompts |

---

### 2026-01-22: Agent Persistence & Parallelization

#### New Features
- **Tracking Module** (`tracking/`): New module for progress, quality, and retry tracking
  - `ProgressTracker`: Weighted phase tracking (plan=10%, execute=50%, verify=15%, etc.)
  - `CodeQualityScore`: Composite quality score with letter grades (A-F)
  - `SmartRetryManager`: Error categorization with adaptive retry strategies
  - `TestResultAggregator`: Flaky test detection and test history tracking

- **Parallel Verification** (`agents/parallel_verifier.py`):
  - Runs syntax, imports, tests, lint, typecheck concurrently
  - Typical 2-3x speedup on multi-core systems
  - `verify_files()` returns detailed results with speedup metrics

- **Overlapping Workflow Phases** (`orchestrator.py`):
  - New `run_workflow_with_overlapping_phases()` method
  - Starts verification when 80% of execution is complete
  - Merges early and final verification results

- **Auto-inject CodeTools** (`orchestrator.py`):
  - Orchestrator now auto-injects `CodeTools` into VerifierAgent
  - Enables real test/lint/typecheck execution instead of stubs

#### Improvements
- **VerifierAgent Persistence** (`agents/verifier.py`):
  - Increased `default_max_tool_calls` from 10 to 25
  - Added retry logic with `max_retries=2` for recoverable failures
  - Improved JSON fallback with heuristic-based success detection

- **ReviewerAgent** (`agents/reviewer.py`):
  - Increased `default_max_tool_calls` to 20

- **RecursionGuard** (`agents/base.py`):
  - Increased `max_total_calls` from 50 to 100 for complex workflows
  - Added `default_max_tool_calls` class attribute to BaseAgent

- **Rich Context Passing** (`orchestrator.py`):
  - Verifier receives detailed execution results summary
  - Reviewer receives verification summary and step descriptions

#### Files Modified
| File | Changes |
|------|---------|
| `orchestrator.py` | Auto-inject CodeTools, overlapping phases, rich context |
| `agents/verifier.py` | max_tool_calls=25, retry logic, improved fallback |
| `agents/reviewer.py` | max_tool_calls=20 |
| `agents/base.py` | default_max_tool_calls, max_total_calls=100 |

#### New Files
| File | Contents |
|------|----------|
| `tracking/__init__.py` | Module exports |
| `tracking/progress.py` | ProgressTracker, WorkflowProgress, PhaseProgress |
| `tracking/quality.py` | CodeQualityScore, QualityGrade |
| `tracking/retry.py` | SmartRetryManager, ErrorCategory, RetryConfig |
| `tracking/test_aggregator.py` | TestResultAggregator, TestHistory |
| `agents/parallel_verifier.py` | ParallelVerifier, CheckResult |

---

### 2026-01-12: UX Designer Integration & Bug Fixes

#### New Features
- **UX Designer Agent in Workflow**: Added `UXDesignerAgent` to the main `Orchestrator` class
  - New workflow phase: `PLAN → UX DESIGN → EXECUTE → VERIFY → REVIEW`
  - Automatically activates for UI/frontend/game tasks (detected via keywords)
  - Skips gracefully for backend-only tasks with "SKIPPED" status in UI
  - Passes UX guidance to ExecutorAgent via `context.previous_step_output`

- **New UXDesignerAgent Methods** (`agents/ux_designer.py`):
  - `design_component(context, component_name, requirements)` → `ComponentDesign`
  - `review_ui(context, requirements)` → `UXReview`
  - Both methods properly connected to LLM providers

- **Web UI Updates**:
  - New "UX" stage in workflow status bar (between PLAN and EXECUTE)
  - "SKIPPED" status with dimmed styling for non-UI tasks
  - Red UX Designer robot activates during UX phase

#### Bug Fixes
- **RecursionGuard False Positives** (`agents/base.py`):
  - Changed from `hash(task_summary[:100])` to `hash(task_summary)` (full hash)
  - Increased threshold from 3 to 5 identical calls
  - Fixes: ExecutorAgent no longer blocked on step 4+ of multi-step workflows

- **Planner JSON Parsing** (`agents/planner.py`):
  - Dependencies now handle both `[1, 2]` and `["step1", "step2"]` formats
  - Gracefully skips malformed steps instead of crashing (KeyError protection)

- **Nested JSON in Files** (`providers/ollama.py`):
  - Added `validate_write_file_content()` to detect nested tool calls in content
  - Extracts actual code when content looks like `{"name": "write_file", ...}`

- **Executor Prompt** (`prompts/executor_prompt.py`):
  - Added explicit instructions to ALWAYS call tools, never just describe actions
  - Clear examples of wrong vs correct behavior

- **UX Phase Status** (`orchestrator.py`):
  - Now correctly emits "error" on failure instead of always "complete"
  - Emits "skipped" for non-UI tasks

#### Files Modified
| File | Changes |
|------|---------|
| `orchestrator.py` | Added UXDesignerAgent, UX phase, `_task_involves_ui()`, `_run_ux_design_phase()` |
| `agents/ux_designer.py` | Added `ComponentDesign` model, `design_component()`, `review_ui()` methods |
| `agents/planner.py` | Fixed dependency parsing, added KeyError protection |
| `agents/base.py` | Fixed RecursionGuard hash and threshold |
| `providers/ollama.py` | Added nested JSON validation for write_file |
| `prompts/executor_prompt.py` | Enforced tool usage |
| `web/templates/index.html` | Added UX stage to workflow status |
| `web/static/js/app.js` | Added ux_design to stageToAgent mapping |
| `web/static/css/retro.css` | Added .skipped styling |

---

## Roadmap / TODO

### Priority 1: Core Functionality
- [ ] Integration tests with Groq API
- [x] Retry logic for rate limits (429 errors)
- [x] Connect real FileTools to agents
- [x] Parallel step execution (`execution/parallel.py`)
- [x] Proactive agent collaboration (`agents/collaboration.py`)

### Priority 2: More Providers
- [x] ClaudeProvider (`providers/claude.py`)
- [x] AzureOpenAIProvider (`providers/azure.py`)
- [x] Provider auto-detection from available API keys

### Priority 3: MCP & Integration
- [x] Test MCP server with Claude Desktop (`tests/test_mcp_server.py`)
- [x] Add MCP resources for project files (`mcp_server.py` - list_resources, read_resource)
- [x] VS Code extension integration (`vscode-extension/`)

### Priority 4: Security & Sandbox
- [x] Build and test Docker sandbox image (`tests/test_sandbox_integration.py`)
- [x] Timeout handling for sandbox execution (`tools/sandbox.py`)
- [x] Resource limits enforcement (memory, CPU, network isolation)

### Priority 5: Web Interface
- [x] Robot idle behavior (wandering, thinking, scanning)
- [x] Collaboration visualization (robots gravitate together)
- [x] WebSocket events for parallel execution
- [x] UX Designer stage in workflow status
- [x] "SKIPPED" status styling for conditional phases
- [x] Streaming output for real-time feedback (router + frontend)
- [x] Token usage dashboard per agent (`app.js` + `/api/hardware/performance`)

### Priority 6: UX Designer Integration
- [x] UXDesignerAgent in main Orchestrator workflow
- [x] `design_component()` and `review_ui()` methods
- [x] Automatic UI task detection via keywords
- [x] UX guidance passed to ExecutorAgent context
- [x] UXDesignerAgent steps in parallel execution (`_run_parallel_ux_design`)
