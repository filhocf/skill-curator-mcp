# RFC-SC-05: Enhanced Onboarding Guide

**Status**: Draft
**Data**: 2026-07-19
**Autor**: Claudio Ferreira Filho / Kiro
**Prioridade**: Alta (sem onboarding claro, agente não usa o MCP corretamente)
**Depende de**: RFC-SC-02 (suggestion field), RFC-SC-04 (integration protocol)

## Problema

O `get_onboarding_guide` atual retorna um JSON minimalista:
- 1 linha de quick_start: "Call skill_match before each task"
- Lista de tools sem contexto de uso
- Nenhum fluxo de lifecycle
- Nenhum threshold explicado
- Nenhum exemplo de integração com hooks

**Consequência**: O agente (Kiro ou outro) não sabe:
- Quando chamar cada tool (startup? pré-tarefa? shutdown?)
- O que fazer com scores de diferentes faixas (<0.5, 0.5-0.7, >0.7)
- Como funciona o ciclo completo (match → use → feedback → gaps → scout → evolve)
- Quais são os thresholds configuráveis
- Como interpretar o campo `suggestion` (SC-02)

O onboarding guide deveria ser **auto-suficiente** — um agente que NUNCA usou o skill-curator
deveria conseguir operar corretamente apenas lendo este guia.

## Requisitos (Prosa + EARS)

### Funcional

**R1**: O guia deve descrever o ciclo completo de vida do uso de skills.

EARS: WHEN `get_onboarding_guide` is called
      THE system SHALL return a structured guide containing:
      - `lifecycle`: description of the full cycle (match → use → feedback → gaps → scout → evolve)
      - `tools`: each tool with when/why/how/example
      - `integration_points`: when to call each tool in a session lifecycle
      - `thresholds`: configurable values and their meanings
      - `examples`: concrete call/response examples

**R2**: Cada tool deve explicar QUANDO usar, com que parâmetros, e como interpretar o resultado.

EARS: The guide SHALL describe each tool with:
      - `when`: trigger condition ("before each task", "at shutdown", etc.)
      - `why`: what problem it solves
      - `parameters`: key params with defaults
      - `interpret`: how to act on the result (score ranges, fields)
      - `example`: one concrete JSON call → response

**R3**: O guia deve incluir o protocolo de integração por momento da sessão.

EARS: The guide SHALL include an `integration_protocol` section with:
      - `startup`: what to call and why
      - `pre_task`: skill_match flow with score interpretation
      - `during_task`: how to follow a matched skill
      - `post_task`: feedback protocol
      - `shutdown`: batch feedback + gap detection
      - `weekly`: audit cycle

**R4**: Aceitar parâmetro de verbosidade para controlar o tamanho do output.

EARS: WHEN `get_onboarding_guide` is called with `verbosity="compact"`
      THE system SHALL return only lifecycle + integration_protocol (≤500 tokens).
      WHEN called with `verbosity="full"` (default)
      THE system SHALL return the complete guide (≤2000 tokens).

**R5**: O guia deve ser atualizado automaticamente quando novas tools são adicionadas.

EARS: WHEN a new tool is registered in the server
      THE onboarding guide SHALL include it in the `tools` section
      WITHOUT requiring manual update to the guide text.

### Não-Funcional

**R6**: O guia deve caber no context budget de um agente (≤2000 tokens full, ≤500 compact).

EARS: The full guide SHALL NOT exceed 2000 tokens.
      The compact guide SHALL NOT exceed 500 tokens.

**R7**: O guia deve ser legível tanto por humano quanto por LLM.

EARS: The guide SHALL use markdown formatting with clear headers and bullet points.

## Design

### Estrutura do retorno (full)

```json
{
  "version": "2.0",
  "lifecycle": "match → use → feedback → gaps → scout → evolve",
  "integration_protocol": {
    "startup": {
      "action": "skill_gaps(correlate=true)",
      "purpose": "Load pending gaps, present to user",
      "frequency": "every session"
    },
    "pre_task": {
      "action": "skill_match(task='...')",
      "purpose": "Find relevant skill before acting",
      "interpret": {
        "score >= 0.7": "Strong match. Read skill file and follow it.",
        "0.5 <= score < 0.7": "Partial match. Follow skill but note it's incomplete.",
        "score < 0.5": "No match. Gap detected and logged. Proceed without skill."
      }
    },
    "post_task": {
      "action": "skill_feedback(name='...', outcome='success|failure', task_description='...')",
      "purpose": "Update skill effectiveness score",
      "frequency": "after each skill use"
    },
    "shutdown": {
      "actions": [
        "skill_feedback (batch from session log)",
        "skill_gaps(correlate=true) → present patterns",
        "suggest scout/evolve if actionable"
      ]
    },
    "weekly": {
      "action": "skill_audit()",
      "purpose": "Full health check: stale, unused, low-effectiveness"
    }
  },
  "tools": {
    "skill_match": {
      "when": "Before every significant task (>15min)",
      "params": {"task": "string (task description)", "top_k": "int (default 3)"},
      "returns": "Top skills with score + suggestion field (SC-02)",
      "example": "skill_match(task='deploy to kubernetes') → [{name:'k8s-deploy', score:0.82}]"
    },
    "skill_feedback": {
      "when": "After using a skill (or at shutdown batch)",
      "params": {"name": "skill name", "outcome": "success|failure|irrelevant", "task_description": "context"},
      "returns": "Updated effectiveness score"
    },
    "skill_gaps": {
      "when": "Startup + shutdown",
      "params": {"correlate": "bool (default false)"},
      "returns": "known_gaps + detected_patterns (if correlate=true)"
    },
    "skill_scout": {
      "when": "When gap is recurrent (>=5 occurrences) or on demand",
      "params": {"query": "search terms", "gaps_only": "bool"},
      "returns": "External skill references with relevance score"
    },
    "skill_evolve": {
      "when": "User explicitly approves skill evolution",
      "params": {"name": "skill to evolve", "context": "what's missing"},
      "returns": "New version of the skill (diff)"
    },
    "skill_audit": {
      "when": "Weekly (first session of the week)",
      "returns": "Health report: stale, unused, low-effectiveness, pending gaps"
    }
  },
  "thresholds": {
    "SKILL_MATCH_HIGH_THRESHOLD": {"default": 0.7, "meaning": "Above = strong match, no suggestion"},
    "SKILL_MATCH_LOW_THRESHOLD": {"default": 0.5, "meaning": "Below = gap detected"},
    "GAP_ACTIONABLE_COUNT": {"default": 3, "meaning": "Occurrences to flag as actionable"},
    "SCOUT_AUTO_TRIGGER": {"default": 5, "meaning": "Occurrences to auto-trigger scout"},
    "STALE_DAYS": {"default": 30, "meaning": "Days without use → stale"},
    "ARCHIVE_DAYS": {"default": 90, "meaning": "Days stale → auto-archive candidate"}
  },
  "scoring_formula": "0.6*similarity + 0.2*effectiveness + 0.2*profile_match; EMA α=0.3"
}
```

### Implementação

O guia é gerado dinamicamente (não hardcoded string):
- `tools` section: introspect registered tools via MCP server registry
- `thresholds`: read from config/env vars
- `version`: bumped when schema changes

### Parâmetro `verbosity`

```python
@mcp.tool()
async def get_onboarding_guide(verbosity: str = "full") -> dict:
    """Get integration guide for using the skill-curator MCP."""
    if verbosity == "compact":
        return {
            "lifecycle": "match → use → feedback → gaps → scout → evolve",
            "integration_protocol": PROTOCOL_COMPACT,
            "thresholds": THRESHOLDS,
        }
    return FULL_GUIDE
```

## Fora de Escopo

- Tutorial interativo (step-by-step conversacional)
- Geração de hooks/steerings a partir do guia
- Multi-idioma (inglês é suficiente — LLMs entendem)

## Critérios de Aceite

- [ ] `get_onboarding_guide()` retorna guia completo com lifecycle + protocol + tools + thresholds
- [ ] `get_onboarding_guide(verbosity="compact")` retorna ≤500 tokens
- [ ] Cada tool tem when/why/params/returns/example
- [ ] `integration_protocol` cobre: startup, pre_task, post_task, shutdown, weekly
- [ ] Thresholds listados com valores default e significado
- [ ] Score interpretation (3 faixas) documentada claramente
- [ ] Guia é auto-suficiente: agente novo opera corretamente só com este guia
- [ ] Testes: verbosity param, tool list matches registered tools, thresholds match config
