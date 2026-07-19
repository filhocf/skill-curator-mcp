# Referência: Skill Curator MCP — Pipeline Completo

**Data:** 2026-07-19 (sirdata)
**Versão:** v0.2.0
**Propósito:** Documento de referência para diagnosticar, corrigir e evoluir o skill-curator-mcp.

---

## 1. O Problema Central

O Kiro CLI tem ~70 skills instaladas mas ativa <5% por sessão. O skill-curator existe para resolver:
1. **Discovery**: encontrar a skill certa para cada tarefa
2. **Feedback loop**: medir se a skill ajudou
3. **Gap detection**: identificar necessidades sem skill cobrindo
4. **Evolution**: melhorar skills com base em feedback
5. **Scout**: buscar skills externas quando há gap recorrente

**Estado ideal:** Agente recebe tarefa → automaticamente encontra skill relevante → segue a skill → reporta resultado → gaps são detectados e corrigidos.

**Estado real (v0.2.0):** Hook de injeção está MORTO (Bug #1 — parseia formato errado). Matching funciona apenas quando agente chama manualmente o MCP tool via steering. Feedback inconsistente. Gaps nunca são correlacionados na prática porque gap_log está vazio.

---

## 2. Arquitetura

### 2.1 Módulos

| Módulo | Função |
|--------|--------|
| `server.py` | FastMCP server, 12 tools registradas, StreamableHTTP porta 3204 |
| `tools.py` | Implementação das 12 tools (match, feedback, gaps, evolve, rollback, etc) |
| `db.py` | SQLite + sqlite-vec, 7 tabelas, CRUD + embedding search |
| `models.py` | Skill, FeedbackEntry, ScoutedSkill, LifecycleState |
| `scoring.py` | cosine_similarity + composite_score (0.6·sim + 0.2·eff + 0.2·profile) |
| `indexer.py` | Scan filesystem → DB (rglob *.md, YAML frontmatter) |
| `scout.py` | Multi-source discovery (GitHub, awesome, pypi, web) + cache 24h |
| `evolution.py` | Evolve skills (section replacement, .versions/ backup, locking) |
| `lifecycle.py` | auto_stale(30d), auto_archive(90d), promotion candidates |
| `audit.py` | Quality scoring por arquivo (frontmatter, length, structure) |
| `profile.py` | Carrega expected_skills de agent profiles JSON |
| `maintenance.py` | Orquestra stale + archive + audit |

### 2.2 DB Schema (7 tabelas)

| Tabela | PK | Propósito |
|--------|-----|-----------|
| `skills` | name | Catálogo principal (70 skills) |
| `skill_embeddings` | name | Vetores 384d cosine (sqlite-vec virtual table) |
| `feedback_log` | id | Histórico de outcomes |
| `skill_evolutions` | id | Versões + corrections |
| `scouted_skills` | id | Resultados de scout |
| `gap_log` | id | Tasks sem match adequado |
| `scout_cache` | query_hash | Cache HTTP 24h |

---

## 3. Bugs Identificados (auditoria 19/jul/2026)

### 🔴 CRÍTICO

| # | Bug | Impacto | Fix |
|---|-----|---------|-----|
| 1 | **Hook response parsing morto** — `user-prompt-submit.sh` parseia `structuredContent.result[]` mas server retorna `content[0].text` (JSON string) | Hook NUNCA injeta skills no contexto. Matching só funciona via chamada manual do agente | Reescrever parser no hook |
| 2 | **`session_id` não exposto no MCP `skill_match`** — server wrapper não passa para tools.py | gap_log sempre tem session_id=NULL, filtro por sessão não funciona | Adicionar param ao server |

### 🟡 MÉDIO

| # | Bug | Impacto | Fix |
|---|-----|---------|-----|
| 3 | `outcome="irrelevant"` não aceito | Shutdown steering pede, mas FeedbackEntry valida só success/partial/failure | Adicionar ao enum |
| 4 | `audit_all` usa `glob` (top-level), indexer usa `rglob` (recursivo) | Skills em subdiretórios auditadas mas não detectadas pelo audit | Usar rglob |
| 5 | `skill_auto_maintain` definida mas nunca registrada no server | Tool dead code | Registrar ou remover |
| 6 | `total_successes` coluna nunca incrementada | Dead data no schema | Remover ou implementar |
| 7 | `profile_tags` coluna nunca populada | Dead data | Remover ou implementar |

### 🟢 BAIXO

| # | Gap | Fix |
|---|-----|-----|
| 8 | Nenhum trigger periódico para maintenance | Adicionar ao startup ou cron |
| 9 | profile.py nunca chamado automaticamente | Integrar no reindex ou startup |
| 10 | Health endpoint duplicado (custom_route + ASGI inline) | Remover custom_route |

---

## 4. Integração com Kiro (Estado Real vs Esperado)

### Hook `user-prompt-submit.sh` (MORTO — Bug #1)

```
ESPERADO: prompt → hook → skill_match → injeta "🎯 Skill: X (path)" no contexto
REAL:     prompt → hook → skill_match → parseia errado → $SKILL_RESULT="" → nada injetado
```

### Steering `work-management.md` (FUNCIONA — manual)

```
ESPERADO: agente lê steering → chama skill_match → segue skill
REAL:     funciona quando o agente LEMBRA de seguir o steering (inconsistente)
```

### Shutdown (PARCIAL)

```
ESPERADO: ler log → skill_feedback batch → skill_gaps(correlate) → apresentar gaps
REAL:     depende de o agente executar o procedimento completo (frequentemente pula steps)
```

---

## 5. Plano de Correção (priorizado)

### Sprint 1 — Desbloquear o hook (CRÍTICO)

1. **Fix Bug #1**: Reescrever parser no hook para extrair de `content[0].text` (JSON string)
2. **Fix Bug #2**: Adicionar `session_id` ao server skill_match
3. **Implementar RFC-SC-04 parcial**: hook injeta path + emite gap/evolve messages
4. **Testar E2E**: enviar prompt → verificar que skill aparece no contexto

### Sprint 2 — Completar integração

5. **Fix Bug #3**: Adicionar "irrelevant" ao FeedbackEntry
6. **Fix Bug #4**: audit rglob
7. **Registrar skill_auto_maintain** no server ou remover
8. **Implementar startup**: skill_gaps(correlate=true) no startup-hook
9. **Implementar shutdown**: batch feedback + gaps presentation

### Sprint 3 — Limpeza e polish

10. Remover colunas mortas (total_successes, profile_tags) ou implementar
11. Trigger periódico para maintenance
12. Profile loading automático no reindex

---

## 6. Como Validar (checklist E2E)

Após cada fix, validar com:

```bash
# 1. Service rodando?
curl -s http://localhost:3204/health

# 2. skill_match retorna com suggestion?
curl -s -X POST http://localhost:3204/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"skill_match","arguments":{"task":"publicar no linkedin"}}}'

# 3. Hook injeta no contexto? (simular prompt)
echo '{"prompt":"publicar no linkedin","session_id":"test"}' | bash ~/.kiro/hooks/user-prompt-submit.sh

# 4. skill_gaps(correlate) retorna estrutura?
curl ... skill_gaps ... correlate=true

# 5. Feedback funciona?
curl ... skill_feedback ... outcome=success

# 6. gap_log popula?
sqlite3 ~/.../skills.db "SELECT * FROM gap_log;"
```

---

## 7. Métricas de Sucesso

| Métrica | Antes (v0.1.x) | Meta (v0.3.0) |
|---------|-----------------|---------------|
| Skills injetadas pelo hook por sessão | 0 (hook morto) | ≥3 |
| Feedback registrados por sessão | 0-1 (manual) | ≥3 (batch automático) |
| Gaps detectados e registrados | 0 (threshold nunca atingido) | ≥1 por sessão com tarefa nova |
| Skills evoluídas com base em gap | 0 | ≥1/mês |
| Latência skill_match p95 | ~200ms | ≤200ms |
