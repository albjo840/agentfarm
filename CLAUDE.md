# CLAUDE.md - AgentFarm

This file provides guidance for Claude Code when working with this repository.

## Project Overview

AgentFarm is a token-efficient multi-agent orchestration system for code tasks. It implements a structured workflow: **PLAN → EXECUTE → VERIFY → REVIEW → SUMMARY**.

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
│   │   ├── verifier.py        # VerifierAgent - testing/validation
│   │   ├── reviewer.py        # ReviewerAgent - code review
│   │   └── ux_designer.py     # UXDesignerAgent - UI/UX design
│   ├── execution/             # Parallel execution system
│   │   ├── __init__.py
│   │   └── parallel.py        # DependencyAnalyzer + ParallelExecutor
│   ├── memory/                # Agent memory system
│   │   ├── base.py            # MemoryManager and base classes
│   │   ├── short_term.py      # In-memory LRU cache
│   │   └── long_term.py       # Persistent JSON storage
│   ├── prompts/               # System prompts per agent
│   │   ├── orchestrator_prompt.py
│   │   ├── planner_prompt.py
│   │   ├── executor_prompt.py
│   │   ├── verifier_prompt.py
│   │   ├── reviewer_prompt.py
│   │   └── ux_designer_prompt.py
│   ├── providers/             # LLM provider implementations
│   │   ├── base.py            # LLMProvider ABC
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
| `execution/parallel.py` | DependencyAnalyzer and ParallelExecutor for concurrent step execution |
| `memory/base.py` | MemoryManager for short/long-term memory |
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
- Use the PLAN→EXECUTE→VERIFY→REVIEW workflow
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
- [ ] Test MCP server with Claude Desktop
- [ ] Add MCP resources for project files
- [ ] VS Code extension integration

### Priority 4: Security & Sandbox
- [ ] Build and test Docker sandbox image
- [ ] Timeout handling for sandbox execution
- [ ] Resource limits enforcement

### Priority 5: Web Interface
- [x] Robot idle behavior (wandering, thinking, scanning)
- [x] Collaboration visualization (robots gravitate together)
- [x] WebSocket events for parallel execution
- [ ] Streaming output for real-time feedback
- [ ] Token usage dashboard per agent
