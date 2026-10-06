# RFC-SC-01: Ampliar Fontes do Scout

**Status**: Draft
**Data**: 2026-07-19
**Autor**: Claudio Ferreira Filho / Kiro
**Prioridade**: Média (depende de SC-02/SC-03 para ter gaps a buscar)
**Depende de**: RFC-SC-02 (gap_log como input para scout direcionado)

## Problema

O `skill_scout` atual busca APENAS no GitHub com queries limitadas:
```python
queries = [s.name for s in skills if s.gap_count > 0]
# Busca: topic:claude-code-skills OR topic:agent-skills
```

Resultado: retorna 0 skills para a maioria dos gaps reais.
**Exemplo**: `skill_scout(query="LinkedIn social media publishing")` → 0 resultados.

## Requisitos (Prosa + EARS)

### Funcional

**R1**: Scout deve buscar em múltiplas fontes, não só GitHub topics.

EARS: WHEN `skill_scout` is called with a query
      THE system SHALL search in MULTIPLE sources (not only GitHub topics).

**R2**: As fontes suportadas devem cobrir o ecossistema relevante.

EARS: The scout SHALL support the following sources:
      - GitHub (expanded: repos search, not just topics)
      - Awesome-lists (awesome-claude-code, awesome-ai-agents, awesome-prompts)
      - PyPI (packages tagged with "mcp", "agent", "skill")
      - Web search (via configured search tool — DuckDuckGo/SearXNG)

**R3**: Quando chamado com gaps_only, usar patterns do gap_log como queries.

EARS: WHEN `skill_scout` is called with `gaps_only=true`
      THE system SHALL use `gap_log` patterns (from SC-02/SC-03) as search queries
      INSTEAD of only using skills with gap_count > 0.

**R4**: Resultados relevantes devem incluir origem, link, score e preview.

EARS: WHEN a scout result has relevance score >= 0.6
      THE system SHALL return it with:
      - `source`: origin (github/pypi/awesome/web)
      - `url`: link to the resource
      - `relevance`: similarity score
      - `content_preview`: first 500 chars or description
      - `suggested_adaptation`: how to adapt for our context

**R5**: Se uma fonte está indisponível, pular sem quebrar.

EARS: IF a source is unreachable (timeout, 403, rate limit)
      THEN THE system SHALL skip that source gracefully
      AND include a `warnings` field in the response.

**R6**: Cachear resultados por 24h para evitar requests repetidos.

EARS: WHILE results are cached (TTL 24h per query)
      THE system SHALL return cached results without re-fetching.

### Não-Funcional

**R7**: Busca total deve completar em tempo aceitável (paralelo).

EARS: Scout SHALL complete within 10s even if all sources are queried (parallel fetch).

**R8**: Limitar requests HTTP por invocação.

EARS: Scout SHALL NOT make more than 10 HTTP requests per invocation.

**R9**: Cache armazenado no banco SQLite existente.

EARS: Cache SHALL be stored in the SQLite database (table `scout_cache`).

## Design

### Source Registry

```python
SOURCES = [
    GitHubSource(
        search_type="repos",
        topics=["agent-skills", "claude-code", "kiro-skills", "mcp-skills"],
    ),
    AwesomeListSource(
        repos=[
            "anthropics/anthropic-cookbook",
            "kirodotdev/awesome-kiro",
            "punkpeye/awesome-mcp-servers",
        ]
    ),
    PyPISource(keywords=["mcp", "agent-skill", "claude-skill"]),
    WebSearchSource(engine="duckduckgo"),  # fallback, no API key needed
]
```

### Nova tabela `scout_cache`

```sql
CREATE TABLE IF NOT EXISTS scout_cache (
    query_hash TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    results_json TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
```

### Parallel Fetch

```python
async def scout(query: str, sources: list[Source] | None = None) -> list[ScoutResult]:
    sources = sources or SOURCES
    tasks = [source.search(query) for source in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Filter exceptions → warnings, flatten results, rank by relevance
```

### Relevance Scoring

Usa embedding do query vs embedding do resultado (descrição/README).
Mesmo modelo (`paraphrase-multilingual-MiniLM-L12-v2`).

## Integração com Kiro (RFC-SC-04 detalha)

Chamado manualmente (`skill_scout(query="...")`) ou automaticamente quando:
- `skill_gaps(correlate=true)` retorna pattern com `recommended_action: "scout_external"`
- Usuário pede explicitamente

## Fora de Escopo

- Download/install automático de skills externas
- Adaptação automática do conteúdo externo
- Criação de PR upstream para compartilhar skills

## Critérios de Aceite

- [ ] `skill_scout` busca em >= 2 fontes (GitHub repos + awesome-lists no mínimo)
- [ ] Cache 24h funcional (segunda chamada retorna sem HTTP)
- [ ] Timeout gracioso (fonte indisponível não quebra o scout)
- [ ] Resultados têm `relevance` score calculado por embedding similarity
- [ ] `gaps_only=true` usa gap_log patterns como queries
- [ ] Latência < 10s com todas fontes (parallel)
- [ ] Testes: cache hit, cache miss, source timeout, relevance ranking
