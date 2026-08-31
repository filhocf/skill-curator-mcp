# Spec: Steering Health Audit (skill-curator-mcp)

**Data**: 2026-06-17
**Autor**: Claudio + Kiro
**Status**: spec pronta, aguardando implementação

## Motivação

Steerings (`~/.kiro/steering/dynamic/*.md`) são injetados em TODA mensagem com `inclusion: always`. Ao longo de semanas acumularam-se 25 steerings always-on com ~50% de redundância — causando compactação precoce ("sessões morrendo rápido"). Nenhum componente monitorava isso.

O skill-curator já tem infra de indexação, embeddings e auditoria para skills. Estender para steerings é natural — mesmo pattern, mesma preocupação (qualidade do harness).

## Escopo

Adicionar ao skill-curator-mcp:
1. Novo módulo `steering.py` — scan, parse, token count, overlap detection
2. Nova tool MCP `steering_audit` — retorna relatório de saúde
3. Integração no startup-hook — rodar junto com `skill_reindex`

## Interface da Tool

```python
@mcp.tool()
def steering_audit(steerings_dir: str | None = None) -> dict:
    """Audit steering files for size, redundancy, and staleness.

    Returns:
        Dict with: total_count, always_count, estimated_tokens,
        overlaps (pairs with cosine >0.85), inflated (>100 lines),
        stale (>60 days without edit), alerts (list of actionable warnings).
    """
```

### Exemplo de retorno

```json
{
  "total_count": 19,
  "always_count": 19,
  "estimated_tokens": 6200,
  "budget_tokens": 8000,
  "health": "ok",
  "overlaps": [
    {"a": "post-approval.md", "b": "external-communication.md", "cosine": 0.92}
  ],
  "inflated": [
    {"name": "lessons-learned.md", "lines": 175}
  ],
  "stale": [
    {"name": "risk-adaptive.md", "days_since_edit": 45}
  ],
  "alerts": [
    "⚠️ 2 steerings com overlap >0.85 — candidatos a consolidação",
    "⚠️ 1 steering inflado (>100 linhas)"
  ]
}
```

## Módulo `steering.py`

```python
"""Steering health auditing."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SteeringFile:
    name: str
    path: str
    inclusion: str  # always | on_demand
    priority: int
    lines: int
    estimated_tokens: int
    last_modified: float  # epoch


@dataclass
class SteeringHealthReport:
    total_count: int
    always_count: int
    estimated_tokens: int
    budget_tokens: int = 8000
    health: str = "ok"  # ok | warning | critical
    overlaps: list[dict] = field(default_factory=list)
    inflated: list[dict] = field(default_factory=list)
    stale: list[dict] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
```

### Lógica

1. **Scan**: glob `*.md` no diretório de steerings
2. **Parse frontmatter**: extrair `inclusion` e `priority`
3. **Token estimation**: `len(content) / 4` (heurística chars/token)
4. **Overlap detection**: embeddings par-a-par dos steerings `always`, alertar se cosine >0.85
5. **Inflated check**: >100 linhas efetivas (excluindo frontmatter e linhas vazias)
6. **Stale check**: `mtime` > 60 dias atrás

### Thresholds

| Métrica | Warning | Critical |
|---------|---------|----------|
| always_count | >15 | >20 |
| estimated_tokens | >8000 | >12000 |
| overlaps (>0.85) | ≥1 | ≥3 |
| inflated (>100 lines) | ≥1 | ≥3 |
| stale (>60 days) | ≥3 | ≥5 |

`health` = "critical" se QUALQUER métrica está em critical, "warning" se alguma está em warning.

## Configuração

```bash
# Env var (default: ~/.kiro/steering/dynamic)
SKILL_CURATOR_STEERINGS_DIR=~/.kiro/steering/dynamic

# Budget personalizável
SKILL_CURATOR_STEERING_BUDGET=8000
```

## Integração no startup-hook

Adicionar ao step 13 do `startup-hook.md`:

```
14. **Steering audit** → `steering_audit()` — se health != "ok", apresentar alerts ao usuário.
```

## Testes

```
test_steering_audit.py:
- test_scan_steerings_dir — encontra .md com frontmatter
- test_parse_frontmatter — extrai inclusion/priority
- test_token_estimation — chars/4 com tolerância ±10%
- test_overlap_detection — 2 arquivos similares → cosine >0.85
- test_inflated_detection — arquivo >100 linhas → flagged
- test_stale_detection — mtime >60 dias → flagged
- test_health_grading — warning vs critical thresholds
- test_empty_dir — retorna counts zero, health ok
```

## Não-escopo (futuro)

- Auto-consolidação (sugerir merge automático)
- Monitorar MEMORY.md e tools list (isso seria o context-budget-monitor — Fase 2)
- Hook pós-compactação (não existe API para isso no Kiro CLI)

## Dependências

- `sentence_transformers` (já existe no skill-curator)
- `sqlite-vec` (já existe)
- Nenhuma dependência nova

## Estimativa

- Módulo `steering.py`: ~80 linhas
- Tool wrapper em `tools.py` + `server.py`: ~20 linhas
- Testes: ~120 linhas
- **Total: ~220 linhas, complexidade 3/10**
