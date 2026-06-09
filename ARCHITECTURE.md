# Arquitetura — Skill Curator MCP

## Diagrama de Componentes

```
┌──────────────────────────────────────────────────────────┐
│                   skill-curator-mcp                       │
│                  (FastMCP, port 3204)                     │
├──────────────┬──────────────┬─────────────┬──────────────┤
│   server.py  │  indexer.py  │ scoring.py  │  scout.py    │
│  (MCP tools) │ (filesystem  │ (rank +     │ (HTTP →      │
│              │  scan + emb) │  feedback)  │  external)   │
├──────────────┴──────────────┴─────────────┴──────────────┤
│                        db.py                              │
│           (SQLite WAL + sqlite-vec + migrations)          │
├──────────────────────────────────────────────────────────┤
│  Storage: ~/.local/share/skill-curator/curator.db         │
└──────────────────────────────────────────────────────────┘
         ↕ StreamableHTTP (localhost:3204)
┌──────────────────────────────────────────────────────────┐
│                     Kiro CLI                              │
│  hook:startup  → skill_reindex()                         │
│  hook:shutdown → skill_gaps()                            │
│  steering      → "call skill_match before every task"    │
└──────────────────────────────────────────────────────────┘
         ↕ Filesystem read-only
┌──────────────────────────────────────────────────────────┐
│  ~/.kiro/skills/**/*.md                                  │
│  ~/.kiro/skills/auto-generated/**/*.md                   │
└──────────────────────────────────────────────────────────┘
```

## Módulos

| Módulo | Responsabilidade |
|--------|-----------------|
| `server.py` | Registro das 8 tools no FastMCP, validação de input |
| `db.py` | Conexão SQLite, migrations, queries parametrizadas |
| `indexer.py` | Scan de filesystem, extração de metadata, geração de embeddings |
| `scoring.py` | Cosine similarity via sqlite-vec, cálculo do score composto |
| `scout.py` | HTTP client (httpx) para skills-manager, GitHub, Anthropic |
| `models.py` | Dataclasses/TypedDicts para Skill, Feedback, Gap, ScoutResult |

## Storage — Schema SQLite

```sql
-- Core: skills indexadas do filesystem
CREATE TABLE skills (
    name TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    description TEXT,
    trigger_text TEXT,
    effectiveness REAL DEFAULT 0.5,
    total_uses INTEGER DEFAULT 0,
    total_successes INTEGER DEFAULT 0,
    gap_count INTEGER DEFAULT 0,
    state TEXT DEFAULT 'active',  -- active|stale|archived|draft
    profile_tags TEXT,            -- JSON array
    last_used_at TEXT,
    last_indexed_at TEXT,
    created_at TEXT
);

-- Histórico de feedback
CREATE TABLE feedback_log (
    id INTEGER PRIMARY KEY,
    skill_name TEXT REFERENCES skills(name),
    session_id TEXT,
    outcome TEXT,  -- success|partial|failure
    task_description TEXT,
    created_at TEXT
);

-- Skills externas descobertas pelo scout
CREATE TABLE scouted_skills (
    id INTEGER PRIMARY KEY,
    source_url TEXT NOT NULL,
    name TEXT,
    description TEXT,
    relevance_score REAL,
    matched_gap TEXT,
    status TEXT DEFAULT 'new',  -- new|adopted|dismissed
    discovered_at TEXT
);

-- Embeddings vetoriais (sqlite-vec)
CREATE VIRTUAL TABLE skill_embeddings USING vec0(
    name TEXT PRIMARY KEY,
    embedding float[384]
);
```

Localização: `~/.local/share/skill-curator/curator.db` com WAL mode.

## Scoring Formula

```
score_final = 0.6 * cosine_similarity + 0.2 * effectiveness + 0.2 * profile_match
```

| Componente | Range | Fonte |
|-----------|-------|-------|
| cosine_similarity | 0.0–1.0 | sqlite-vec: embedding(task) vs embedding(skill.description + trigger) |
| effectiveness | 0.0–1.0 | EMA com α=0.3, default 0.5 |
| profile_match | 0.0 ou 1.0 | 1.0 se skill.name ∈ profile.expected_skills |

EMA update: `new_eff = α * outcome_value + (1-α) * old_eff`
- success = 1.0, partial = 0.5, failure = 0.0

## Lifecycle State Machine

```
         skill_promote() OR
         (eff > 0.7 && uses >= 3)
  draft ──────────────────────────→ active
                                      │
                           no use 30d │
                                      ▼
                                    stale
                                   │     │
                          used again│     │ no use 90d OR eff < 0.3
                                   ▼     ▼
                                active  archived
                                          │
                              skill_promote()
                                          │
                                          ▼
                                        active
```

Estados: `draft` → `active` → `stale` → `archived`
Qualquer estado pode retornar a `active` via `skill_promote()`.

## Integração com Kiro CLI

| Hook | Momento | Tool chamada |
|------|---------|--------------|
| startup | Início de sessão CAO | `skill_reindex()` |
| shutdown | Fim de sessão | `skill_gaps()` |
| steering | Antes de cada task delegada | `skill_match(task)` |

O steering injeta skills retornadas no system prompt do worker via context.

## Decisões Técnicas

### Por que FastMCP (não Flask/raw HTTP)?
- SDK oficial do protocolo MCP — garante compatibilidade com tools, resources, prompts.
- StreamableHTTP built-in, sem boilerplate de transport.
- Type-safe tool registration com decorators.

### Por que sqlite-vec (não FAISS/Chroma)?
- Zero infra extra — single file, embeddable no mesmo SQLite do estado.
- Performance suficiente para <1000 skills (nosso caso).
- Queries combinam filtros SQL + KNN sem join externo.

### Por que separado do memory-service?
- Responsabilidades distintas: memory = episódico/long-term; curator = operacional/runtime.
- Ciclo de release independente — curator pode iterar sem risco de regressão no memory.
- Dados diferentes: memory guarda texto livre; curator guarda metadata estruturada + embeddings de skills.
- Acesso concurrent: memory é read-heavy; curator é write-heavy durante reindex.

### Por que MiniLM-L6-v2?
- 384 dims — leve para sqlite-vec.
- Latência <50ms por embedding em CPU.
- Qualidade suficiente para matching de descriptions curtas (1-3 frases).
