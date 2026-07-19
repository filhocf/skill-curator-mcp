# RFC-SC-03: Gap Detection Correlacionada

**Status**: Draft
**Data**: 2026-07-19
**Autor**: Claudio Ferreira Filho / Kiro
**Prioridade**: Média (complementa SC-02, dá visibilidade real)
**Depende de**: RFC-SC-02 (gap_log table)

## Problema

O `skill_gaps()` atual retorna apenas skills com `gap_count > 0` ou sem uso recente.
Isso NÃO detecta gaps REAIS porque:

1. `gap_count` só incrementa manualmente (ou via SC-02 quando implementado)
2. Não correlaciona com o que o agente REALMENTE fez na sessão
3. Uma tarefa pode ser executada com sucesso SEM skill — isso não aparece como gap

**Exemplo real**: Claudio pediu "postar no LinkedIn" 3 vezes em 2 meses.
Cada vez o agente usou `personal-branding` com score 0.56 e improvisou.
O sistema nunca detectou que publicação em redes sociais é um gap recorrente.

## Requisitos (Prosa + EARS)

### Funcional

**R1**: Quando chamado com correlação, agrupar gaps similares do log por tema.

EARS: WHEN `skill_gaps` is called with `correlate=true`
      THE skill-curator SHALL cross-reference the `gap_log` table
      AND return patterns grouped by similarity (tasks que pedem coisas parecidas mas sem skill).

**R2**: Quando um pattern de gap aparece 3+ vezes, marcar como acionável com recomendação.

EARS: WHEN a gap pattern has >= 3 occurrences in `gap_log`
      THE skill-curator SHALL flag it as `actionable`
      AND include a `recommended_action` field ("create_skill" | "evolve_skill" | "scout_external").

**R3**: Opcionalmente aceitar lista de tasks completadas para cruzar com skills usadas.

EARS: WHERE `task_orchestrator` integration is enabled
      THE skill-curator SHALL accept a `tasks_completed` parameter
      AND cross-reference tasks completed vs skills used to detect systematic gaps.

**R4**: Usar similaridade semântica para clustering (mesmo modelo de embeddings).

EARS: The gap correlation SHALL use semantic similarity (same embedding model)
      to cluster related gap_log entries (threshold: cosine similarity >= 0.8).

**R5**: Retornar resultado estruturado com gaps conhecidos + patterns detectados + recomendações.

EARS: WHEN the user calls `skill_gaps(correlate=true)`
      THE system SHALL return:
      - `known_gaps`: skills with gap_count > 0 (current behavior)
      - `detected_patterns`: clusters of similar unmatched tasks from gap_log
      - `recommendations`: actionable items with priority

### Não-Funcional

**R6**: Completar correlação em tempo aceitável mesmo com log grande.

EARS: Gap correlation SHALL complete within 500ms for up to 1000 gap_log entries.

**R7**: Clustering determinístico (reproduzível).

EARS: Clustering SHALL be deterministic (same input = same output) given fixed embeddings.

## Design

### Nova tool: `skill_gaps` enhanced

```python
@mcp.tool()
async def skill_gaps(
    correlate: bool = False,
    session_id: str | None = None
) -> dict:
    """Detect skill gaps — enhanced with correlation."""
    
    result = {"known_gaps": [...]}  # current behavior
    
    if correlate:
        # 1. Fetch gap_log entries
        entries = db.get_gap_log(session_id=session_id)
        
        # 2. Cluster by semantic similarity
        clusters = cluster_by_similarity(entries, threshold=0.8)
        
        # 3. Flag actionable patterns (>=3 occurrences)
        patterns = []
        for cluster in clusters:
            if len(cluster) >= 3:
                patterns.append({
                    "theme": summarize_cluster(cluster),
                    "occurrences": len(cluster),
                    "first_seen": cluster[0].timestamp,
                    "last_seen": cluster[-1].timestamp,
                    "sample_tasks": [e.task_description for e in cluster[:3]],
                    "closest_existing_skill": cluster[0].best_match_name,
                    "recommended_action": determine_action(cluster),
                    "actionable": True
                })
        
        result["detected_patterns"] = patterns
        result["recommendations"] = generate_recommendations(patterns)
    
    return result
```

### Clustering

Usa o mesmo modelo de embeddings (`paraphrase-multilingual-MiniLM-L12-v2`) já carregado.
Gera embedding para cada `task_description` no gap_log, clusteriza com threshold 0.8.

### Determine Action Logic

```python
def determine_action(cluster):
    avg_score = mean(e.best_match_score for e in cluster)
    if avg_score < 0.3:
        return "create_skill"  # Nada remotamente parecido
    elif avg_score < 0.6:
        return "evolve_skill"  # Existe algo próximo, precisa expandir
    else:
        return "scout_external"  # Skill existe mas é fraca — buscar referências
```

## Integração com Kiro (RFC-SC-04 detalha)

No shutdown (step 4 — `skill_gaps`):
```
skill_gaps(correlate=true) → apresentar patterns ao usuário
Se pattern actionable: "⚠️ Gap recorrente: {theme} ({N}x). Criar skill?"
```

No startup semanal (ou sob demanda):
```
skill_gaps(correlate=true) → dashboard de gaps
```

## Fora de Escopo

- Criação automática da skill a partir do pattern
- Integração direta com task-orchestrator (futuro, quando SC-03 R3 for implementado)
- Web scraping de referências (isso é RFC-SC-01)

## Critérios de Aceite

- [ ] `skill_gaps(correlate=true)` retorna clusters semanticamente similares
- [ ] Clusters com >= 3 entradas são marcados `actionable`
- [ ] `recommended_action` diferencia create/evolve/scout baseado em score médio
- [ ] Latência < 500ms para 1000 entries no gap_log
- [ ] Backward-compatible: `skill_gaps()` sem param mantém comportamento atual
- [ ] Testes: cluster formation, threshold boundary, empty gap_log, large gap_log
