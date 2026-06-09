# PRD — Skill Curator MCP

## Problema

Agentes IA possuem 30+ skills instaladas mas ativam menos de 5% por sessão. Causas:

1. **Sem discovery**: o agente não sabe quais skills existem ou quando usá-las.
2. **Sem feedback loop**: não há medição se uma skill ajudou ou atrapalhou.
3. **Sem lifecycle**: skills ficam obsoletas, duplicadas ou subutilizadas sem que ninguém perceba.

O resultado é trabalho manual repetido e skills que apodrecem no filesystem.

## Personas

| Persona | Papel | Necessidade |
|---------|-------|-------------|
| Kiro (orquestrador) | Decide qual skill ativar antes de cada task | Ranking semântico + efetividade |
| Worker dev-python | Implementa código seguindo skills ativas | Saber quais skills se aplicam ao contexto |
| Worker reviewer | Valida output contra convenções | Feedback se a skill ajudou |
| Claudio (humano) | Curadoria estratégica | Dashboard de lifecycle, gaps, scouts |

## Features (8 tools)

1. **skill_match** — busca semântica + scoring para encontrar skills relevantes.
2. **skill_feedback** — registra outcome (success/partial/failure) com EMA scoring.
3. **skill_gaps** — detecta padrões de tarefas sem skill correspondente.
4. **skill_lifecycle** — relatório de estado: active, stale, candidatas a promote/archive.
5. **skill_promote** — transiciona draft → active.
6. **skill_archive** — desativa com preservação e motivo.
7. **skill_reindex** — rescan do filesystem, regenera embeddings.
8. **skill_scout** — busca skills externas correlacionadas com gaps locais.

## Critérios de Aceite

- >30% das sessões orquestradas ativam pelo menos 1 skill via curator.
- Latência p95 de skill_match < 200ms (embeddings locais).
- Feedback loop reduz gap_count médio em 20% após 2 semanas de uso.
- skill_scout retorna resultados relevantes (>0.6 relevance) para 50%+ dos gaps.

## Fora de Escopo

- **CRUD de arquivos de skill** — responsabilidade do skills-manager.
- **Marketplace de conteúdo** — responsabilidade do daymade.
- **Execução de skills** — o curator recomenda, não executa.
- **Edição de prompts** — curator não modifica conteúdo das skills.
- **Auth/multi-tenant** — servidor local single-user.

## User Stories

### US-1: Match semântico na abertura de task
> Como orquestrador Kiro, quero receber as top-3 skills relevantes para a task atual, para injetá-las no contexto do worker.

Acceptance: `skill_match("implementar endpoint REST")` retorna skills com score > 0.5.

### US-2: Feedback pós-execução
> Como reviewer, quero registrar se a skill recomendada ajudou, para que o scoring se ajuste automaticamente.

Acceptance: após 5 feedbacks "success", effectiveness sobe de 0.5 para >0.7.

### US-3: Detecção de gaps
> Como Claudio, quero ver quais tipos de tarefa não têm skill cobrindo, para decidir se crio ou busco externamente.

Acceptance: `skill_gaps()` retorna clusters de tasks sem match > 0.4.

### US-4: Lifecycle automático
> Como orquestrador, quero que skills sem uso em 30 dias sejam marcadas stale automaticamente, para não poluir resultados.

Acceptance: `skill_lifecycle()` lista transições pendentes com motivo.

### US-5: Scout externo
> Como Claudio, quero que o sistema busque skills públicas que cobrem meus gaps, para avaliar adoção.

Acceptance: `skill_scout(gaps_only=true)` retorna skills externas com matched_gap preenchido.
