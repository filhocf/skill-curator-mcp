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

## Features (9 tools)

| # | Tool | Descrição | Status |
|---|------|-----------|--------|
| 1 | `skill_match` | Busca semântica + composite scoring | ✅ v0.2 |
| 2 | `skill_feedback` | Registra outcome com EMA scoring | ✅ v0.2 |
| 3 | `skill_gaps` | Detecta skills com gap_count ou stale | ✅ v0.2 |
| 4 | `skill_lifecycle` | Relatório: active, stale, candidates | ✅ v0.2 |
| 5 | `skill_promote` | Transiciona para active | ✅ v0.2 |
| 6 | `skill_archive` | Desativa com preservação | ✅ v0.2 |
| 7 | `skill_reindex` | Rescan filesystem + embeddings | ✅ v0.2 |
| 8 | `skill_scout` | Busca skills externas (GitHub) | ✅ v0.3 |
| 9 | `get_onboarding_guide` | Guia de integração para MCP clients | ✅ v1.0 |

## Features v1.0

| Feature | Descrição | Status |
|---------|-----------|--------|
| Multilíngue | Embedding model paraphrase-multilingual-MiniLM-L12-v2 | ✅ |
| Profile-aware matching | Boost para skills em agent profile expected_skills | ✅ |
| Auto-evolution | auto_stale (30d) + auto_archive (90d) + generate_draft_skill | ✅ |
| Scout real | GitHub API search com cache 24h | ✅ |
| Multi-machine sync | hot-backup + restore scripts (VACUUM INTO) | ✅ |
| ADR process | docs/decisions/001-cosine-distance.md | ✅ |

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

Acceptance: `skill_match("implementar endpoint REST")` retorna skills com score > 0.5. ✅

### US-2: Feedback pós-execução
> Como reviewer, quero registrar se a skill recomendada ajudou, para que o scoring se ajuste automaticamente.

Acceptance: após 5 feedbacks "success", effectiveness sobe de 0.5 para >0.7. ✅

### US-3: Detecção de gaps
> Como Claudio, quero ver quais tipos de tarefa não têm skill cobrindo, para decidir se crio ou busco externamente.

Acceptance: `skill_gaps()` retorna skills com gap_count > 0 ou stale. ✅

### US-4: Lifecycle automático
> Como orquestrador, quero que skills sem uso em 30 dias sejam marcadas stale automaticamente.

Acceptance: `auto_stale()` transiciona skills inativas; `auto_archive()` remove stale >90d. ✅

### US-5: Scout externo
> Como Claudio, quero que o sistema busque skills públicas que cobrem meus gaps.

Acceptance: `skill_scout(gaps_only=True)` retorna skills externas com matched_gap preenchido. ✅

## Roadmap v1.1

| Feature | Descrição | Prioridade |
|---------|-----------|------------|
| `skill_audit` | Relatório cross-session: uso por skill, tendências, recomendações de curadoria | Alta |
| Audit persistence | Tabela audit_reports com snapshots periódicos | Média |
| Integration dashboard | Output formatado para consumo por memory-service | Baixa |
