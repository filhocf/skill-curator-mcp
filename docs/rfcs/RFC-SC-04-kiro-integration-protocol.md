# RFC-SC-04: Kiro Integration Protocol

**Status**: Draft
**Data**: 2026-07-19
**Autor**: Claudio Ferreira Filho / Kiro
**Prioridade**: Alta (sem isso, SC-01/02/03 não têm efeito)
**Depende de**: RFC-SC-02, RFC-SC-03

## Problema

O skill-curator-mcp tem 9+ tools mas o Kiro usa efetivamente apenas 2:
- `skill_match` (via hook user-prompt-submit.sh — injeta nome, não conteúdo)
- `skill_gaps` + `skill_feedback` (no shutdown, se lembrar)

**Gaps de integração identificados:**

| Ponto de contato | O que deveria acontecer | O que acontece HOJE |
|------------------|------------------------|---------------------|
| Hook injeta skill | Deveria injetar conteúdo ou path legível | Injeta só NOME → agente precisa ler manualmente |
| Match < 0.5 | Deveria registrar gap + avisar | SILÊNCIO total |
| Match 0.5-0.7 | Deveria sugerir evolução | Trata como match normal |
| Pós-tarefa | Deveria dar feedback | Só no shutdown (se log existir) |
| skill_scout | Deveria rodar quando gap é recorrente | NUNCA é chamado automaticamente |
| skill_evolve | Deveria rodar quando skill é fraca | NUNCA é chamado automaticamente |
| skill_audit | Deveria rodar periodicamente | NUNCA é chamado |
| Startup | Deveria reportar gaps pendentes | Não reporta |

## Requisitos (Prosa + EARS)

### Hook: user-prompt-submit.sh

**R1**: Quando há match, injetar nome + path da skill (não só nome).

EARS: WHEN `skill_match` returns score >= 0.5
      THE hook SHALL inject into context:
      - Skill name
      - Skill description
      - Skill file path (so the agent can `read` it)

**R2**: Quando não há match (gap), avisar e registrar no log local.

EARS: WHEN `skill_match` returns `suggestion.gap_detected: true` (score < 0.5)
      THE hook SHALL inject into context:
      - "⚠️ Nenhuma skill cobre esta tarefa ({suggested_name}). Gap registrado."
      - Log entry in `$STATE_DIR/skill_gaps_detected.log`

**R3**: Quando match é parcial (0.5-0.7), sugerir evolução.

EARS: WHEN `skill_match` returns `suggestion.improvement_opportunity: true` (0.5 ≤ score < 0.7)
      THE hook SHALL inject into context:
      - "💡 Skill `{name}` é parcial para esta tarefa (score: {score}). Considerar evoluir."

### Steering: work-management.md (seção pré-tarefa)

**R4**: Ao receber tarefa significativa, chamar skill_match e agir conforme score.

EARS: WHEN the agent receives a significant task (>15min)
      THE agent SHALL call `skill_match(task="{resumo}")`
      AND IF score >= 0.5: read the skill file and follow it
      AND IF score < 0.5: acknowledge the gap and proceed without skill.

### Steering: shutdown-hook.md

**R5**: No encerramento, registrar feedback batch e apresentar gaps ao usuário.

EARS: WHEN the session ends (partial or complete)
      THE agent SHALL:
      1. Read `$STATE_DIR/skill_matches.log` → call `skill_feedback` for each
      2. Read `$STATE_DIR/skill_gaps_detected.log` → present gaps to user
      3. Call `skill_gaps(correlate=true)` → present actionable patterns
      4. IF actionable pattern with >= 3 occurrences: suggest "Criar skill? (skill_evolve ou manual)"

### Steering: startup-hook.md

**R6**: No startup, carregar gaps pendentes silenciosamente e incluir no resumo.

EARS: WHEN a session starts (Fase 3 — background)
      THE agent SHALL call `skill_gaps(correlate=true)` silently
      AND IF there are actionable patterns not yet resolved:
      - Store in memory for reference during session
      - Present in startup summary: "🎯 Gaps pendentes: {theme} ({N}x)"

### Periódico: Semanal

**R7**: Na primeira sessão da semana, rodar auditoria completa de skills.

EARS: WHILE it is the first session of the week (Monday or first startup after 5+ days)
      THE agent SHALL run `skill_audit()` and present summary:
      - Skills nunca usadas (>30d)
      - Skills com effectiveness < 0.3
      - Gaps actionable não resolvidos
      - Sugestão de scout para gaps recorrentes

### Trigger: skill_scout automático

**R8**: Quando gap é muito recorrente (>=5x), buscar referências externas automaticamente.

EARS: WHEN `skill_gaps(correlate=true)` returns a pattern with:
      - `recommended_action: "scout_external"` AND
      - `occurrences >= 5` (threshold alto para não ser intrusivo)
      THE agent SHALL call `skill_scout(query="{pattern.theme}")`
      AND present results to user: "🔍 Encontrei {N} referências externas para `{theme}`. Quer que eu adapte?"

### Trigger: skill_evolve

**R9**: Evolução de skill só dispara com aprovação explícita do usuário.

EARS: WHEN the user explicitly approves evolution ("sim", "evolui", "melhora a skill")
      THE agent SHALL call `skill_evolve(name="{skill}", context="{task_descriptions from gap_log}")`
      AND present the diff to the user for approval.

## Design: Mudanças nos Artefatos Kiro

### 1. user-prompt-submit.sh (patch)

```bash
# Atual: injeta só nome
echo "🎯 Skill match: $SKILL_RESULT"

# Proposto: injetar nome + path + sugestão
if [[ -n "$SUGGESTION_GAP" ]]; then
  echo "⚠️ Nenhuma skill cobre esta tarefa. Gap: $SUGGESTED_NAME"
  echo "${NOW}|${SUGGESTED_NAME}|gap|${PROMPT_SHORT}" >> "$STATE_DIR/skill_gaps_detected.log"
elif [[ -n "$SUGGESTION_EVOLVE" ]]; then
  echo "💡 Skill \`$SKILL_NAME\` parcial (score: $SCORE). Considerar evoluir."
  echo "📖 Path: ~/.kiro/skills/${SKILL_NAME}.md"
else
  echo "🎯 Skill: $SKILL_NAME (score: $SCORE)"
  echo "📖 Path: ~/.kiro/skills/${SKILL_NAME}.md"
fi
```

### 2. shutdown-hook.md (adicionar step 4c)

```markdown
### 4c. Gaps detectados na sessão
Ler `$STATE_DIR/skill_gaps_detected.log`
Se existir: apresentar ao usuário resumo dos gaps
Se gap apareceu >=3x (correlate): sugerir ação
```

### 3. startup-hook.md (adicionar em Fase 3)

```markdown
### Background: Skill gaps pendentes
skill_gaps(correlate=true) → se actionable: "🎯 Gaps: {theme} ({N}x)"
```

### 4. work-management.md (atualizar seção pré-tarefa)

```markdown
### Ao receber pedido novo
- `skill_match(task="<resumo>")`:
  - score >=0.7: seguir skill (ler o .md)
  - score 0.5-0.7: seguir skill + anotar que é parcial
  - score <0.5: reconhecer gap, prosseguir sem skill
```

## Fora de Escopo

- Mudanças no MCP server (SC-02/SC-03 cobrem)
- Criação automática de skills sem aprovação humana
- Integração com task-orchestrator (futuro)

## Critérios de Aceite

- [ ] Hook injeta path da skill (não só nome)
- [ ] Hook reporta gap quando score < 0.5
- [ ] Hook reporta improvement opportunity quando 0.5 ≤ score < 0.7
- [ ] Shutdown apresenta gaps da sessão ao usuário
- [ ] Startup (background) carrega gaps pendentes
- [ ] Semanal: skill_audit roda na primeira sessão da semana
- [ ] skill_scout disparado automaticamente quando gap >= 5 ocorrências
- [ ] skill_evolve disparado APENAS com aprovação explícita do usuário
- [ ] Nenhuma ação destrutiva sem confirmação humana

## Diagrama de Fluxo

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SESSÃO KIRO                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STARTUP                                                            │
│  └─ skill_gaps(correlate=true) → "🎯 Gaps: {theme}"                 │
│                                                                     │
│  CADA PROMPT (hook)                                                 │
│  └─ skill_match(task) →                                             │
│       ├─ score >=0.7 → "🎯 Skill: {name}" + path                    │
│       ├─ 0.5-0.7    → "💡 Parcial: {name}" + path                   │
│       └─ <0.5       → "⚠️ Gap: {suggested}" + log                   │
│                                                                     │
│  DURANTE (agente)                                                   │
│  └─ Se skill matched → read skill .md → seguir                      │
│  └─ Após usar skill → skill_feedback(outcome)                       │
│                                                                     │
│  SHUTDOWN                                                           │
│  ├─ skill_feedback (batch do log)                                   │
│  ├─ skill_gaps(correlate=true) → apresentar patterns                │
│  ├─ Se gap >=5x → skill_scout → apresentar resultados               │
│  └─ Se usuário aprova → skill_evolve                                │
│                                                                     │
│  SEMANAL                                                            │
│  └─ skill_audit() → report completo                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
