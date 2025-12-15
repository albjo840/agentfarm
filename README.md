# AgentFarm

Token-efficient multi-agent orchestration system for code tasks.

## Features

- **Multi-agent workflow**: PLAN → EXECUTE → VERIFY → REVIEW → SUMMARY
- **Token efficiency**: Minimal context per agent, summarized handoffs
- **Provider abstraction**: Ollama (free), Groq (free tier), Claude, Azure
- **Docker sandbox**: Safe code execution in isolated containers
- **MCP server**: Integrate with Claude Desktop, VS Code, etc.

## Installation

```bash
# Basic installation (uses Ollama by default)
pip install agentfarm

# With specific provider
pip install agentfarm[claude]
pip install agentfarm[ollama]

# Development
pip install agentfarm[dev]
```

## Quick Start

### CLI Usage

```bash
# Run full workflow
agentfarm workflow "Add a function to calculate fibonacci"

# Plan only
agentfarm plan "Refactor the authentication module"

# Run as MCP server
agentfarm mcp
```

### Python API

```python
import asyncio
from agentfarm import Orchestrator
from agentfarm.providers.ollama import OllamaProvider

async def main():
    provider = OllamaProvider(model="llama3.2")
    orchestrator = Orchestrator(provider, working_dir="./my_project")

    result = await orchestrator.run_workflow(
        task="Add unit tests for the utils module",
        context_files=["src/utils.py"],
    )

    print(result.pr_summary)

asyncio.run(main())
```

## Architecture

```
┌─────────────────┐
│   Orchestrator  │
└────────┬────────┘
         │
    ┌────┴────┬─────────┬──────────┐
    ▼         ▼         ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Planner │ │Executor│ │Verifier│ │Reviewer│
└────────┘ └────────┘ └────────┘ └────────┘
                │
                ▼
         ┌────────────┐
         │Docker      │
         │Sandbox     │
         └────────────┘
```

## Configuration

Environment variables:
- `AGENTFARM_PROVIDER`: ollama, groq, claude, azure_openai
- `AGENTFARM_MODEL`: Model name (e.g., llama3.2, gpt-4)
- `AGENTFARM_API_KEY`: API key for provider
- `OLLAMA_HOST`: Ollama server URL (default: http://localhost:11434)

## License

MIT
