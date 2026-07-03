# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.2.0] - 2026-07-03

### Added
- `evolution.py` — skill auto-correction loop (RFC-skill-evolution.md)
- `skill_evolve` tool — apply corrections to skill content with versioning
- `skill_rollback` tool — restore previous version from `.versions/`
- `skill_evolutions` table — tracks all evolution events
- Version preservation: `.versions/{name}.{timestamp}.md` before overwrite
- Safety guards: min 2 failures + 1h cooldown + dry_run default
- `tests/test_evolution.py` — 17 unit tests for evolution module
- Integration tests for skill_evolve + skill_rollback in test_tools.py
- docs/RFC-skill-evolution.md — full RFC document
- Integration guide updated with evolve/rollback steps

### Changed
- Server now exposes 12 tools (was 10)
- Effectiveness resets to 0.5 after evolution (skill must re-prove)

## [1.0.0] - 2026-06-10

### Added
- `profile.py` — carrega expected_skills de agent profiles (~/.kiro/agents/)
- `scoring.py` — cosine_similarity e composite_score (0.6/0.2/0.2)
- Modelo multilíngue: paraphrase-multilingual-MiniLM-L12-v2
- Multi-machine sync: `scripts/hot-backup.sh` + `scripts/restore-from-sync.sh`
- ADR 001: cosine distance para embeddings (fix score=0.1 para tudo)
- 9ª tool: `get_onboarding_guide`
- Testes: test_profile.py, test_multilingual.py (total: 106)

### Changed
- Embedding table usa `distance_metric=cosine` (antes: L2 default)
- Similarity formula: `1.0 - distance/2.0` (range cosine 0-2)
- `skill_match` aceita parâmetro `profile` para boost de profile_match

## [0.4.0] - 2026-06-10

### Added
- `lifecycle.py` — auto_stale (30d), auto_archive (90d + eff<0.3)
- `detect_promotion_candidates` — drafts com eff>0.7 e uses>=3
- `generate_draft_skill` — cria skill draft a partir de gap recorrente
- `skill_auto_maintain` em tools.py (stale + archive em sequência)
- test_lifecycle.py

## [0.3.0] - 2026-06-10

### Added
- `scout.py` — busca GitHub (topic:claude-code-skills OR agent-skills)
- Cache 24h de scouted_skills no DB
- Modo `gaps_only` — usa gap names como queries
- test_scout.py

## [0.2.0] - 2026-06-09

### Added
- `server.py` — FastMCP com 8 tools registradas (StreamableHTTP)
- `tools.py` — implementação das 8 tools MCP
- test_tools.py, test_server.py

## [0.1.0] - 2026-06-09

### Added
- `models.py` — Skill, FeedbackEntry, LifecycleState, ScoutedSkill
- `db.py` — SQLite + sqlite-vec, CRUD, embeddings, feedback_log
- `indexer.py` — scan filesystem, parse frontmatter YAML, reindex_all
- `scorer.py` — scoring auxiliar (predecessor de scoring.py)
- test_models.py, test_db.py, test_indexer.py, test_scorer.py
- CI: GitHub Actions (pytest)
