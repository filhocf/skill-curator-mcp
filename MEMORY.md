# Memory — Skill Curator MCP

## Estado Atual

- **Versão**: v1.0.0
- **Status**: implementado e em uso
- **Testes**: 106 (unitários + parametrizados)
- **Tools**: 9 (skill_match, skill_feedback, skill_gaps, skill_lifecycle, skill_promote, skill_archive, skill_reindex, skill_scout, get_onboarding_guide)

## Decisões Tomadas

- FastMCP (SDK oficial MCP) como framework — StreamableHTTP, porta 3204
- sqlite-vec para embeddings (single-file, WAL mode)
- **paraphrase-multilingual-MiniLM-L12-v2** (384 dims) — suporte multilíngue
- Separado do memory-service (responsabilidades distintas)
- EMA α=0.3 para feedback scoring
- Score: 0.6 semantic + 0.2 effectiveness + 0.2 profile_match
- Cosine distance (ADR 001) — similarity = 1 - dist/2
- Skills dir: `~/.kiro/skills/**/*.md`
- Storage: `~/.local/share/skill-curator/curator.db`
- Multi-machine sync via hot-backup + restore scripts

## Histórico

| Data | Evento |
|------|--------|
| 2026-06-09 | Scaffold + README + docs (v0.0) |
| 2026-06-09 | v0.1.0 — core: models, db, indexer, scorer |
| 2026-06-09 | v0.2.0 — tools + server (8 MCP tools) |
| 2026-06-10 | v0.3.0 — scout real (GitHub API, caching) |
| 2026-06-10 | v0.4.0 — lifecycle automation (auto_stale, auto_archive, draft generation) |
| 2026-06-10 | v1.0.0 — multilíngue, profile.py, scoring.py, multi-machine sync, ADR 001 |

## Próximo

- **v1.1**: `skill_audit` — relatório de uso cross-session com recomendações
