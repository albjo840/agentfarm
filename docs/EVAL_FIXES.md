# Eval Regression Fixes

> **Datum:** 2026-01-24
> **Score:** 51.4% → 76.2% (+25%)

## Sammanfattning

Denna dokument beskriver fixarna som löste eval-regressionen och höjde score från 51.4% till 76.2%.

## Problem

### 1. Pydantic Validation Errors

**Symptom:** `ValidationError: severity - Input should be a valid string`

**Orsak:** LLM returnerade `null` för fält som förväntade sig strings/lists.

```python
# Buggy code:
severity = c.get("severity", "info")  # Returns None if key exists but value is null

# Fixed:
severity = c.get("severity") or "info"  # Falls back to "info" on None
```

**Filer:**
- `agents/verifier.py` - `lint_issues`, `type_errors`, `tests_passed`, etc.
- `agents/reviewer.py` - `ReviewComment.severity`

### 2. LLM Path Hallucination

**Symptom:** `ERROR: File not found: /home/user/project/main.py`

**Orsak:** LLM hallucinerade absolute paths istället för relativa.

**Fix 1 - Path validation:**
```python
try:
    file_path.resolve().relative_to(self._working_dir)
except ValueError:
    return "ERROR: Path outside working directory. Use relative paths."
```

**Fix 2 - Show available files:**
```python
available = [f.name for f in self._working_dir.iterdir()][:10]
return f"ERROR: File not found. Available: {available}"
```

### 3. Tool Call Loops

**Symptom:** `Agent VerifierAgent hit max_tool_calls limit (40)`

**Orsak:** LLM försökte samma icke-existerande path om och om igen.

**Fix - Track failed paths:**
```python
self._failed_paths: set[str] = set()

async def _read_file(self, path: str) -> str:
    if path in self._failed_paths:
        return "ERROR: Already tried this path - skip it."

    if not file_path.exists():
        self._failed_paths.add(path)
        return "ERROR: File not found."
```

### 4. Fuzzy Matching Bug

**Symptom:** `Content to replace not found in file.py`

**Orsak:** Regex operations i fel ordning.

```python
# Buggy:
search_pattern = re.sub(r'\s+', r'\\s+', re.escape(search.strip()))
# re.escape() körs FÖRE whitespace normalisering

# Fixed:
search_normalized = re.sub(r'\s+', ' ', search.strip())  # 1. Normalize
search_escaped = re.escape(search_normalized)            # 2. Escape
search_pattern = search_escaped.replace(r'\ ', r'\s+')  # 3. Flex whitespace
```

### 5. Parallel Execution Hiding Errors

**Symptom:** Files not created but no error reported

**Orsak:** `stop_on_failure=False` dolde fel i parallell exekvering.

**Fix:**
```python
# orchestrator.py
stop_on_failure=True,  # Stop early to catch errors

# Plus file existence verification:
for result in results:
    if result.success and result.files_changed:
        for fc in result.files_changed:
            if not (Path(self.working_dir) / fc.path).exists():
                result.success = False
```

## Prompt Improvements

Lade till PATH RULES i system prompts för Verifier och Reviewer:

```markdown
## PATH RULES (CRITICAL):
- Use ONLY relative paths like "main.py", "src/utils.py"
- NEVER use absolute paths like /home/... or /tmp/...
- NEVER use ~ or $HOME
- If a file doesn't exist after 2 attempts, skip it
- Don't keep retrying the same file path
```

## Resultat

| Kategori | Före | Efter | Förändring |
|----------|------|-------|------------|
| codegen | 69.2% | 70% | +1% |
| bugfix | 75% | 81% | +6% |
| refactor | 24.4% | 60% | **+36%** |
| multistep | 94% | 95% | +1% |
| **Total** | **51.4%** | **76.2%** | **+25%** |

## Testning

```bash
# Kör unit tests
python -m pytest tests/ -v
# 227 passed, 20 skipped

# Kör eval suite
python -m evals.suite
# 7/11 passed, 76.2% score

# Kör enskilt test
python -m evals.suite --test codegen-001
```

## Filer som Ändrades

| Fil | Ändringar |
|-----|-----------|
| `agents/verifier.py` | Null handling, path tracking, validation, prompts |
| `agents/reviewer.py` | Null handling, path tracking, validation, prompts |
| `agents/base.py` | MD5 hash för RecursionGuard |
| `orchestrator.py` | stop_on_failure=True, fil-verifiering |
| `providers/ollama.py` | JSON fence pattern |
| `tools/file_tools.py` | Fuzzy matching fix |
| `evals/suite.py` | --test output fix |

## Kvarvarande Förbättringsmöjligheter

1. **Bättre edit_file matching** - Hantera fler whitespace-variationer
2. **Smarter retry logic** - Anpassa efter feltyp
3. **Context injection** - Ge agenter mer info om tillgängliga filer från start
4. **Model fine-tuning** - Träna modeller på korrekt path-användning
