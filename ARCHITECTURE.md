# Arquitetura — Skill Curator MCP

## Diagrama de Componentes

```
┌──────────────────────────────────────────────────────────┐
│                   skill-curator-mcp                       │
│                  (FastMCP, port 3204)                     │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ server.py│indexer.py│scoring.py│ scout.py │ lifecycle.py │
│(9 tools) │(scan+emb)│(rank+    │(GitHub   │(auto-stale   │
│          │          │ composite│ search)  │ auto-archive)│
├──────────┼──────────┴──────────┴──────────┴──────────────┤
│profile.py│                  db.py                         │
│(agent    │      (SQLite WAL + sqlite-vec + cosine)        │
│ profiles)│                                                │
├──────────┴───────────────────────────────────────────────┤
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
| `server.py` | Registro das 9 tools no FastMCP, lazy init de DB e encoder |
| `tools.py` | Lógica de negócio das tools (match, feedback, gaps, lifecycle, scout) |
| `db.py` | Conexão SQLite WAL, sqlite-vec, CRUD skills/feedback/scouted |
| `indexer.py` | Scan filesystem, parse frontmatter YAML, geração de embeddings |
| `scoring.py` | `cosine_similarity` e `composite_score` (0.6/0.2/0.2) |
| `scorer.py` | Scoring auxiliar (legacy, predecessor de scoring.py) |
| `scout.py` | HTTP client (httpx) para GitHub search + cache 24h |
| `lifecycle.py` | `auto_stale`, `auto_archive`, `detect_promotion_candidates`, `generate_draft_skill` |
| `profile.py` | Carrega `expected_skills` de agent profiles JSON (~/.kiro/agents/) |
| `models.py` | Dataclasses: Skill, FeedbackEntry, ScoutedSkill; Enum: LifecycleState |

## Embedding Model

**paraphrase-multilingual-MiniLM-L12-v2** (sentence-transformers)

- 384 dimensões
- Suporte multilíngue (50+ idiomas)
- Latência <50ms por embedding em CPU
- Configurável via `SKILL_CURATOR_MODEL` env var

## Storage — Schema SQLite

```sql
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
    profile_tags TEXT,
    last_used_at TEXT,
    last_indexed_at TEXT,
    created_at TEXT
);

CREATE TABLE feedback_log (
    id INTEGER PRIMARY KEY,
    skill_name TEXT REFERENCES skills(name),
    session_id TEXT,
    outcome TEXT,  -- success|partial|failure
    task_description TEXT,
    created_at TEXT
);

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

CREATE VIRTUAL TABLE skill_embeddings USING vec0(
    name TEXT PRIMARY KEY,
    embedding float[384] distance_metric=cosine
);
```

Localização: `~/.local/share/skill-curator/curator.db` com WAL mode.

## Scoring Formula

```
score_final = 0.6 * cosine_similarity + 0.2 * effectiveness + 0.2 * profile_match
```

| Componente | Range | Fonte |
|-----------|-------|-------|
| cosine_similarity | 0.0–1.0 | `1.0 - cosine_distance/2.0` (sqlite-vec cosine distance range 0–2) |
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
                           no use 30d │ (auto_stale)
                                      ▼
                                    stale
                                   │     │
                          used again│     │ no use 90d OR eff < 0.3 (auto_archive)
                                   ▼     ▼
                                active  archived
                                          │
                              skill_promote()
                                          │
                                          ▼
                                        active
```

## Multi-machine Sync

Sync via filesystem (ex: Dropbox, git, rsync):

- `scripts/hot-backup.sh` — `VACUUM INTO` para criar cópia consistente
- `scripts/restore-from-sync.sh` — restaura DB se local ausente no startup
- Destino configurável: `SKILL_CURATOR_SYNC_DIR` (default: `~/dtp/ai-configs/global`)

## Integração com Kiro CLI

| Hook | Momento | Tool chamada |
|------|---------|--------------|
| startup | Início de sessão | `skill_reindex()` |
| shutdown | Fim de sessão | `skill_gaps()` |
| steering | Antes de cada task | `skill_match(task, profile=...)` |

## Decisões Técnicas

### Por que FastMCP?
SDK oficial MCP — StreamableHTTP built-in, type-safe tool registration.

### Por que sqlite-vec com cosine distance?
Single file, zero infra. Performance OK para <1000 skills. Ver [ADR 001](docs/decisions/001-cosine-distance.md).

### Por que separado do memory-service?
Responsabilidades distintas (episódico vs operacional), ciclo de release independente, patterns de acesso diferentes.

### Por que paraphrase-multilingual-MiniLM-L12-v2?
Suporte a skills escritas em português/inglês/espanhol sem reindexação por idioma. Mesmo tamanho (384d) que o L6 monolíngue anterior.
