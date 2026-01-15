# AgentFarm LLM Providers

> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [AGENTS.md](./AGENTS.md)

## Översikt

AgentFarm stödjer flera LLM-providers med automatisk fallback:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PROVIDER HIERARCHY                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Priority 1: Ollama (Lokal)                                            │
│  └── Gratis, ingen rate limit, full kontroll                           │
│      Modeller: qwen2.5-coder:7b, llama3.2, phi4                        │
│                                                                         │
│  Priority 2: Groq (Free Tier)                                          │
│  └── Snabb, 100k tokens/dag                                            │
│      Modeller: llama-3.3-70b-versatile                                 │
│                                                                         │
│  Priority 3: Gemini (Free Tier)                                        │
│  └── 15 RPM limit, 1M tokens/min                                       │
│      Modeller: gemini-1.5-flash                                        │
│                                                                         │
│  Priority 4: SiliconFlow/Qwen (Free Tier)                              │
│  └── Qwen-modeller                                                     │
│      Modeller: Qwen/Qwen2.5-7B-Instruct                                │
│                                                                         │
│  Priority 5: Claude (Paid)                                             │
│  └── Högsta kvalitet, för komplexa uppgifter                          │
│      Modeller: claude-sonnet-4-20250514                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Provider-klasser

### Base Provider (`providers/base.py`)

```python
from agentfarm.providers.base import LLMProvider, CompletionResponse

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        **kwargs
    ) -> CompletionResponse:
        ...

    async def stream(self, messages, **kwargs):
        # Optional streaming
        yield "token"
```

### CompletionResponse

```python
@dataclass
class CompletionResponse:
    content: str
    input_tokens: int
    output_tokens: int
    tool_calls: list[ToolCall] | None = None
    model: str | None = None
```

## Providers

### 1. Ollama (Lokal) - `providers/ollama.py`

```python
from agentfarm.providers.ollama import OllamaProvider

provider = OllamaProvider(
    model="qwen2.5-coder:7b",
    base_url="http://localhost:11434",
)

response = await provider.complete([
    {"role": "user", "content": "Write hello world in Python"}
])
```

**Features:**
- Context truncation (anpassar till modellens max_tokens)
- Nested JSON validation (fixar tool calls i content)
- Retry logic för transient errors

**Rekommenderade modeller:**
| Modell | Bäst för | VRAM |
|--------|----------|------|
| qwen2.5-coder:7b | Kodgenerering | ~6GB |
| qwen3:14b | Komplex reasoning | ~10GB |
| phi4 | Kod + matematik | ~8GB |
| llama3.2 | Generellt | ~4GB |

### 2. Groq - `providers/groq.py`

```python
from agentfarm.providers.groq import GroqProvider

provider = GroqProvider(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
)
```

**Free Tier Limits:**
- 100,000 tokens/dag
- Mycket snabb inference

### 3. Gemini - `providers/gemini.py`

```python
from agentfarm.providers.gemini import GeminiProvider

provider = GeminiProvider(
    model="gemini-1.5-flash-latest",
    api_key=os.getenv("GOOGLE_API_KEY"),
)
```

**Free Tier Limits:**
- 15 requests per minute (strikt!)
- 1M tokens/min

### 4. SiliconFlow - `providers/siliconflow.py`

```python
from agentfarm.providers.siliconflow import SiliconFlowProvider

provider = SiliconFlowProvider(
    model="Qwen/Qwen2.5-7B-Instruct",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
)
```

### 5. Claude - `providers/claude.py`

```python
from agentfarm.providers.claude import ClaudeProvider

provider = ClaudeProvider(
    model="claude-sonnet-4-20250514",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
)
```

### 6. Azure OpenAI - `providers/azure.py`

```python
from agentfarm.providers.azure import AzureProvider

provider = AzureProvider(
    deployment_name="gpt-4",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)
```

## LLM Router (`providers/router.py`)

Multi-model routing baserat på task type:

```python
from agentfarm.providers.router import LLMRouter, TaskType

router = LLMRouter(event_bus=event_bus)
await router.initialize()  # Kollar tillgängliga modeller

response, model_used = await router.complete(
    messages=[{"role": "user", "content": "..."}],
    task_type=TaskType.CODE_GENERATION,
)
print(f"Användes: {model_used}")  # e.g., "qwen2.5-coder:7b"
```

### Task Types

| TaskType | Bästa modeller |
|----------|----------------|
| `CODE_GENERATION` | qwen2.5-coder, phi4 |
| `CODE_REVIEW` | qwen2.5-coder |
| `PLANNING` | qwen3:14b, llama3.2 |
| `REASONING` | qwen3:14b |
| `VERIFICATION` | gemma2:9b |
| `MATH` | phi4 |
| `GENERAL` | llama3.2 |

## Multi-Provider Mode (`multi_provider.py`)

Automatisk provider-val per agent:

```python
from agentfarm.multi_provider import get_agent_provider

# Returns optimal provider for each agent
planner_provider = get_agent_provider("planner")
executor_provider = get_agent_provider("executor")
```

**Default mapping:**
- Alla agenter → Ollama (lokal, ingen rate limit)
- Fallback: Groq → Gemini → SiliconFlow

## Token Management

### Truncation Strategy (`base.py`)

```python
def truncate_messages(messages, max_tokens):
    """
    Bevarar:
    1. System message (alltid)
    2. Senaste meddelanden (prioriteras)

    Trunkerar:
    - Äldre user/assistant meddelanden
    - Stora code blocks
    """
```

### Token Estimation

```python
def estimate_tokens(text: str) -> int:
    """Approximerar tokens: ~4 chars per token"""
    return len(text) // 4
```

## Environment Variables

```bash
# Free tier providers
GROQ_API_KEY=gsk_...
GOOGLE_API_KEY=AIza...
GEMINI_API_KEY=AIza...        # Alias för GOOGLE_API_KEY
SILICONFLOW_API_KEY=sk-...

# Paid providers
ANTHROPIC_API_KEY=sk-ant-...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://....openai.azure.com/

# Local
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b

# Override
AGENTFARM_PROVIDER=ollama     # Force specific provider
AGENTFARM_MODEL=llama3.2      # Force specific model
```

## Retry & Error Handling

```python
# Alla providers har inbyggd retry logic
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0

# 429 (rate limit) → exponential backoff
# 500/502/503 → retry med delay
# 400/401/403 → fail immediately
```

---

*Se även: [AGENTS.md](./AGENTS.md) för hur agenter använder providers*
