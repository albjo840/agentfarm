# MCP-Based Testing for AgentFarm

> **Uppdaterad:** 2026-01-23
>
> Se även: [INDEX.md](./INDEX.md) | [AGENTS.md](./AGENTS.md)

## Översikt

AgentFarm exponerar 10 nya MCP-verktyg för testning och introspection via Claude Desktop. Dessa verktyg möjliggör:

- Körning av evalueringssviten direkt från Claude
- Introspection av agent-prompter
- Snabbtester av systemkomponenter
- Testning av individuella agenter

## Installation

MCP-verktygen aktiveras automatiskt när du kör AgentFarm som MCP-server:

```bash
agentfarm mcp
```

### Claude Desktop Configuration

Lägg till i `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentfarm": {
      "command": "agentfarm",
      "args": ["mcp"],
      "cwd": "/path/to/your/project",
      "env": {
        "OLLAMA_HOST": "localhost:11434"
      }
    }
  }
}
```

## Tillgängliga Verktyg

### Evaluation Tools (4 st)

| Verktyg | Beskrivning |
|---------|-------------|
| `run_eval` | Kör evalueringssviten med valfri kategorifiltrering |
| `list_evals` | Lista alla tillgängliga evalueringstester |
| `run_single_eval` | Kör ett specifikt test via ID |
| `get_eval_results` | Hämta senaste evalueringsresultat |

#### Exempel: list_evals

```json
{
  "tests": [
    {"id": "codegen-001", "name": "Simple Function", "category": "codegen", "points": 10},
    {"id": "bugfix-001", "name": "Fix Off-by-One Error", "category": "bugfix", "points": 10}
  ],
  "count": 11
}
```

#### Exempel: run_eval

```json
// Input
{"category": "codegen"}

// Output
{
  "success": true,
  "tests_run": 4,
  "tests_passed": 3,
  "tests_failed": 1,
  "total_score": 43.0,
  "max_score": 65.0,
  "percentage": 66.2,
  "duration_seconds": 653.0
}
```

### Prompt Introspection Tools (3 st)

| Verktyg | Beskrivning |
|---------|-------------|
| `get_prompt` | Hämta system prompt för en agent |
| `list_prompts` | Lista alla agent-prompter med metadata |
| `test_prompt` | Testa en prompt med sample input |

#### Agenter som stöds

- `planner` - Planeringsagent
- `executor` - Kodexekveringsagent
- `verifier` - Verifieringsagent
- `reviewer` - Kodgranskningsagent
- `ux_designer` - UI/UX-designagent
- `orchestrator` - Koordineringsagent

#### Exempel: get_prompt

```json
// Input
{"agent": "planner"}

// Output
{
  "agent": "planner",
  "prompt": "You are a task planning agent...",
  "length": 1028,
  "has_custom_suffix": false
}
```

### Workflow Testing Tools (3 st)

| Verktyg | Beskrivning |
|---------|-------------|
| `test_agent` | Testa en enskild agent med specifik input |
| `run_quick_test` | Kör snabba sanity-tester |

#### Exempel: run_quick_test

```json
// Input
{"component": "imports"}

// Output
{
  "all_passed": true,
  "results": {
    "imports": {"passed": true}
  }
}
```

Tillgängliga komponenter: `imports`, `agents`, `tools`, `memory`

## Modulstruktur

```
src/agentfarm/mcp/
├── __init__.py          # Module exports med lazy imports
├── schemas.py           # Pydantic response-schemas
├── eval_tools.py        # EvalToolHandler
├── prompt_tools.py      # PromptToolHandler
└── testing_tools.py     # TestingToolHandler
```

### Schemas

```python
class EvalRunResult(BaseModel):
    success: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    total_score: float
    max_score: float
    percentage: float
    duration_seconds: float
    report_path: str | None = None
    by_category: dict | None = None

class PromptInfo(BaseModel):
    agent: str
    prompt: str
    length: int
    has_custom_suffix: bool

class AgentTestResult(BaseModel):
    agent: str
    success: bool
    output: str
    summary: str
    tokens_used: int | None = None
    duration_seconds: float
```

## Evalueringsresultat (2026-01-23)

### Baseline med Ollama (qwen2.5-coder:7b + llama3.2)

| Kategori | Passerade | Poäng | Procent |
|----------|-----------|-------|---------|
| codegen | 3/4 | 43/65 | 66.2% |
| bugfix | 2/3 | 35/40 | 87.5% |
| refactor | 0/2 | 14/40 | 35.1% |
| multistep | 1/2 | 19/65 | 29.4% |
| **TOTALT** | **6/11** | **111/210** | **52.9%** |

### Detaljerade Resultat

**Codegen (3/4 PASS):**
- Simple Function - 80%
- Calculator Class - 100%
- REST API Endpoint - 100%
- Data Processing Pipeline - 0% (FAIL)

**Bugfix (2/3 PASS):**
- Fix Race Condition - 100%
- Fix SQL Injection - 100%
- Fix Off-by-One Error - Timeout

**Refactor (0/2 PASS):**
- Extract Method - 33%
- Replace Conditionals - 71%

**Multistep (1/2 PASS):**
- Web Scraper - 88%
- CLI Todo App - 60%

### Identifierade Problem

1. **edit_file-verktyget** - Matchar inte filinnehåll korrekt ("Content to replace not found")
2. **Tool call limits** - VerifierAgent (25) och ReviewerAgent (20) når max-gränser
3. **run_tests API** - `keywords`-argument stöds ej i CodeTools
4. **ProactiveCollaborator** - Ej konfigurerad men agenterna försöker använda den
5. **Timeout** - Vissa tester tar >300s

## Tester

```bash
# Kör MCP-verktygstester
python -m pytest tests/test_mcp_tools.py -v

# Resultat: 15 passed
```

### Testfil: tests/test_mcp_tools.py

Testar:
- EvalToolHandler (list_evals, get_eval_results)
- PromptToolHandler (get_prompt, list_prompts, set_custom_prompt)
- TestingToolHandler (run_quick_test)
- Pydantic schemas (EvalRunResult, PromptInfo, AgentTestResult)

## Användning med Parallella Subagenter

MCP-testverktygen kan köras parallellt för snabbare resultat:

```python
# Köra evalueringar parallellt per kategori
# (sparar ~50% tid jämfört med sekventiell körning)

categories = ["codegen", "bugfix", "refactor", "multistep"]
# Starta 4 parallella agenter, en per kategori
```

---

*Dokumentationen genererad: 2026-01-23*
