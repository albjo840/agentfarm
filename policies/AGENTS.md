# AgentFarm Policy

## Repository Guidelines

This document defines the rules and conventions for the AgentFarm multi-agent system.

## Workflow: PLAN → EXECUTE → VERIFY → REVIEW → SUMMARY

All changes must follow this workflow:

1. **PLAN** - Break down the task into small, verifiable steps
2. **EXECUTE** - Implement changes using available tools
3. **VERIFY** - Run tests and validation
4. **REVIEW** - Code review against standards
5. **SUMMARY** - Create PR description

## Agent Responsibilities

### PlannerAgent
- Analyzes task requirements
- Breaks down into atomic steps
- Estimates complexity
- **Tools**: `read_file`, `list_directory`, `search_code`

### ExecutorAgent
- Implements code changes
- One file at a time
- Small, focused commits
- **Tools**: `read_file`, `write_file`, `edit_file`, `run_in_sandbox`

### VerifierAgent
- Runs test suite
- Checks linting/formatting
- Validates type hints
- **Tools**: `run_tests`, `run_linter`, `run_typecheck`

### ReviewerAgent
- Reviews code quality
- Checks for security issues
- Validates against patterns
- **Tools**: `read_file`, `get_diff`, `add_comment`

## Code Standards

### Python
- Python 3.10+
- Type hints required
- Pydantic for data models
- Async/await for I/O operations
- Ruff for linting and formatting

### Testing
- pytest for all tests
- Minimum 80% coverage for new code
- Unit tests for each agent
- Integration tests for workflow

### Security
- No secrets in code
- All code execution in Docker sandbox
- Input validation on all tools
- Sanitize file paths

## Token Efficiency

To minimize token usage:

1. **Focused context** - Each agent receives only relevant information
2. **Summarization** - Pass summaries between agents, not full history
3. **Lazy loading** - Read files only when needed
4. **Filtered outputs** - Only pass relevant tool results forward

## File Conventions

```
src/agentfarm/
├── agents/          # One file per agent
│   ├── base.py      # BaseAgent ABC
│   ├── planner.py   # PlannerAgent
│   ├── executor.py  # ExecutorAgent
│   ├── verifier.py  # VerifierAgent
│   └── reviewer.py  # ReviewerAgent
├── providers/       # LLM provider implementations
│   ├── base.py      # LLMProvider ABC
│   ├── ollama.py    # Free, local
│   ├── groq.py      # Free tier
│   ├── claude.py    # Anthropic
│   └── azure.py     # Azure AI Foundry
├── tools/           # Agent tools
└── models/          # Pydantic schemas
```

## Commit Messages

Format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

Example: `feat(agents): add PlannerAgent with task breakdown`

## Change Size

- Maximum 200 lines per change
- One logical change per commit
- If larger, split into multiple steps
