# RFC-SC-02: Sugestão Proativa de Nova Skill

**Status**: Draft
**Data**: 2026-07-19
**Autor**: Claudio Ferreira Filho / Kiro
**Prioridade**: Alta (valor imediato, baixa complexidade)

## Problema

QUANDO o agente recebe uma tarefa e `skill_match` retorna score < 0.5 (nenhuma skill relevante),
o sistema atual fica em SILÊNCIO — nenhuma ação é tomada, nenhum gap é registrado.

O usuário não sabe que não há skill para o tema. O gap_count não incrementa.
Na próxima vez que a mesma necessidade surgir, o mesmo silêncio se repete.

**Exemplo real**: "postar no LinkedIn" → best match `personal-branding` com 0.56, seção de posts fraca.
O curator deveria ter sugerido: "não há skill específica para publicação em redes sociais. Criar?"

## Requisitos (Prosa + EARS)

### Funcional

**R1**: Quando nenhuma skill cobre a tarefa (score < 0.5), retornar sugestão de criação.

EARS: WHEN `skill_match` is called AND the best score < 0.5
      THE skill-curator SHALL return a `suggestion` field with:
      - `gap_detected`: true
      - `closest_match`: {name, score}
      - `suggested_action`: "create_new" | "evolve_existing"
      - `suggested_name`: snake_case name derived from task description

**R2**: Quando uma skill cobre parcialmente (score 0.5-0.7), sugerir evolução.

EARS: WHEN `skill_match` is called AND the best score is between 0.5 and 0.7
      THE skill-curator SHALL return a `suggestion` field with:
      - `gap_detected`: false
      - `improvement_opportunity`: true
      - `closest_match`: {name, score}
      - `suggested_action`: "evolve_existing"

**R3**: Ao detectar gap, registrar para tracking futuro (gap_log + gap_count).

EARS: WHEN a suggestion with `gap_detected: true` is returned
      THE skill-curator SHALL increment `gap_count` for the closest matching skill
      AND log the unmatched task description in a `gap_log` table.

**R4**: Quando um gap aparece 3+ vezes, permitir geração automática de draft.

EARS: WHILE `gap_count` for a gap pattern reaches >= 3
      THE skill-curator SHALL be capable of generating a draft skill via `generate_draft_skill`.

### Não-Funcional

**R5**: A sugestão não pode degradar a performance do skill_match.

EARS: The suggestion field SHALL NOT increase `skill_match` latency by more than 10ms (p95).

**R6**: O gap_log deve armazenar contexto suficiente para análise posterior.

EARS: The `gap_log` table SHALL store: timestamp, task_description, best_match_name, best_match_score, session_id.

## Design

### Mudanças no `skill_match` return shape

```python
# Antes:
{"name": "personal-branding", "score": 0.56, "description": "..."}

# Depois (score >= 0.7):
{"name": "personal-branding", "score": 0.72, "description": "..."}

# Depois (0.5 <= score < 0.7):
{
    "name": "personal-branding",
    "score": 0.56,
    "description": "...",
    "suggestion": {
        "gap_detected": false,
        "improvement_opportunity": true,
        "closest_match": {"name": "personal-branding", "score": 0.56},
        "suggested_action": "evolve_existing",
    },
}

# Depois (score < 0.5):
{
    "name": null,
    "score": 0.0,
    "suggestion": {
        "gap_detected": true,
        "closest_match": {"name": "personal-branding", "score": 0.43},
        "suggested_action": "create_new",
        "suggested_name": "linkedin-social-media-publishing",
    },
}
```

### Nova tabela `gap_log`

```sql
CREATE TABLE IF NOT EXISTS gap_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    task_description TEXT NOT NULL,
    best_match_name TEXT,
    best_match_score REAL,
    session_id TEXT,
    resolved INTEGER DEFAULT 0
);
```

### Thresholds (configuráveis via env)

| Env Var | Default | Significado |
|---------|---------|-------------|
| `SKILL_MATCH_HIGH_THRESHOLD` | 0.7 | Score acima = match confiável, sem sugestão |
| `SKILL_MATCH_LOW_THRESHOLD` | 0.5 | Score abaixo = gap detectado |

## Integração com Kiro (RFC-SC-04 detalha)

O hook `user-prompt-submit.sh` já chama `skill_match`. Quando receber `suggestion.gap_detected: true`:
1. Injetar no contexto: "⚠️ Nenhuma skill cobre esta tarefa. Sugestão: criar `{suggested_name}`"
2. Logar em `$STATE_DIR/skill_gaps_detected.log`
3. No shutdown, apresentar gaps detectados ao usuário

## Fora de Escopo

- Criação automática da skill (isso é `skill_evolve` — já existe)
- Busca externa automática (isso é RFC-SC-01)
- Correlação com tasks do orchestrator (isso é RFC-SC-03)

## Critérios de Aceite

- [ ] `skill_match` retorna `suggestion` quando score < 0.7
- [ ] `gap_log` é populado quando score < 0.5
- [ ] `gap_count` incrementa para closest match quando gap detectado
- [ ] Latência p95 skill_match ≤ 210ms (hoje ~200ms)
- [ ] Testes cobrem: score >=0.7, 0.5-0.7, <0.5, gap_count increment
