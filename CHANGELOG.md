# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-07-19

### Added
- **RFC-SC-02**: Proactive suggestion field in `skill_match` — 3-tier response:
  - score ≥ 0.7: strong match (no suggestion)
  - 0.5 ≤ score < 0.7: `improvement_opportunity: true`, suggests evolving existing skill
  - score < 0.5: `gap_detected: true`, logs to `gap_log` table, increments `gap_count`
- **RFC-SC-03**: Correlated gap detection — `skill_gaps(correlate=true)`:
  - Semantic clustering of gap_log entries (pure Python, no numpy/scipy)
  - `detected_patterns` with occurrences, actionable flag, recommended_action
  - Actions: `create_skill` (avg <0.3), `evolve_skill` (0.3-0.6), `scout_external` (≥0.6)
- **RFC-SC-05**: Enhanced `get_onboarding_guide(verbosity)`:
  - `verbosity="full"`: lifecycle, integration_protocol, tools (with when/params/returns), thresholds, scoring_formula
  - `verbosity="compact"`: lifecycle + protocol only (≤500 tokens)
  - Version field, auto-documents all registered tools
- **RFC-SC-01**: Multi-source scout with cache:
  - `sources` parameter (github, awesome, pypi, web — expandable)
  - `scout_cache` table with 24h TTL (SHA256 query hash)
  - Gap_log integration: `gaps_only=true` uses gap_log patterns as queries
  - Graceful failure: source exceptions → `warnings` field (not crash)
  - Max 10 HTTP requests per invocation
  - `source` field on every result
- **RFC-SC-04**: Kiro Integration Protocol documented (hooks/steerings update pending)
- New tables: `gap_log`, `scout_cache`
- `session_id` parameter on `skill_match`
- 5 RFCs in `docs/rfcs/`
- Gap analysis doc in `docs/research/`
- 27 new tests (total: 159)

### Changed
- `get_onboarding_guide` signature: accepts `verbosity` and `db` params (backward compatible)
- `skill_gaps` signature: accepts `correlate` and `encoder` params (backward compatible)
- `scout_skills` signature: accepts `sources` param (backward compatible)
- EARS notation adopted for all specs (prosa + EARS dual format)

## [0.1.2] - 2026-07-03

### Fixed
- Force CPU for embeddings on incompatible GPU (CUDA_VISIBLE_DEVICES="")
- Updated uv.lock

## [0.1.1] - 2026-06-11

### Fixed
- sqlite-vec virtual tables don't support `INSERT OR REPLACE` — use DELETE+INSERT pattern

### Added
- Eval framework with 3 evals (001-cosine-fix, 002-execution-stack, 003-onboarding-guide)
- `skill_audit` tool (v1.1) with periodic maintenance recommendations
- Daily maintenance scheduler (auto_stale + auto_archive)
- Multi-machine sync scripts (hot-backup.sh + restore-from-sync.sh)
- Multilingual embedding model (paraphrase-multilingual-MiniLM-L12-v2)
- Profile-aware matching (`profile` parameter in skill_match)
- ADR 001: cosine distance for embeddings
- 9th tool: `get_onboarding_guide`
- `lifecycle.py` — auto_stale (30d), auto_archive (90d + eff<0.3)
- `generate_draft_skill` — creates skill draft from recurrent gap
- `scout.py` — GitHub search (topic:claude-code-skills OR agent-skills)
- Cache 24h for scouted_skills
- `scoring.py` — composite_score (0.6*similarity + 0.2*effectiveness + 0.2*profile_match)
- Tests: 132 total (test_profile, test_multilingual, test_lifecycle, test_scout, test_tools, test_server)

### Changed
- Embedding table uses `distance_metric=cosine` (was: L2 default)
- Similarity formula: `1.0 - distance/2.0` (cosine range 0-2)

## [0.1.0] - 2026-06-09

### Added
- Initial implementation (TDD-first)
- `models.py` — Skill, FeedbackEntry, LifecycleState, ScoutedSkill
- `db.py` — SQLite + sqlite-vec, CRUD, embeddings, feedback_log
- `indexer.py` — filesystem scan, YAML frontmatter parse, reindex_all
- `server.py` — FastMCP with StreamableHTTP transport
- `tools.py` — 8 MCP tools (skill_match, skill_feedback, skill_gaps, skill_lifecycle, skill_promote, skill_archive, skill_reindex, skill_scout)
- CI: GitHub Actions (pytest on push/PR)
- 56 tests

[Unreleased]: https://github.com/filhocf/skill-curator-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/filhocf/skill-curator-mcp/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/filhocf/skill-curator-mcp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/filhocf/skill-curator-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/filhocf/skill-curator-mcp/releases/tag/v0.1.0
