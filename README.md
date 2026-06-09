# skill-curator-mcp

Skill lifecycle intelligence for AI agents. Matches tasks to skills semantically, tracks effectiveness, detects gaps, and scouts external sources.

## Problem

AI agents have 30+ skills but activate <5% per session. Skills exist but the agent doesn't know when to use them. No feedback loop measures if a skill actually helped.

## Solution

An MCP server that provides **intelligent skill routing** — not CRUD (skills-manager does that) nor a marketplace (daymade does that), but the missing intelligence layer:

1. **Semantic matching**: embed skills + task → cosine similarity + effectiveness boost
2. **Feedback loop**: EMA scoring tracks what works
3. **Gap detection**: identifies missing skills from session patterns
4. **Scout**: searches external sources (skills-manager marketplace, GitHub) correlated with local gaps

## Tools (8)

| Tool | Purpose |
|------|---------|
| `skill_match(task, profile?, top_k=3)` | Find best skills for current task |
| `skill_feedback(name, outcome, session_id?)` | Record success/partial/failure |
| `skill_gaps(session_id?, profile?)` | Detect uncovered task patterns |
| `skill_lifecycle()` | Report: active, stale, candidates for promote/archive |
| `skill_promote(name)` | Move draft → active |
| `skill_archive(name, reason?)` | Deactivate with preservation |
| `skill_reindex()` | Rescan filesystem, regenerate embeddings |
| `skill_scout(query?, gaps_only=false)` | Search external skill sources |

## Architecture

```
┌─────────────────────────────────────────┐
│            skill-curator-mcp            │
│         (FastMCP, port 3204)            │
├─────────────────────────────────────────┤
│  Index Layer (sqlite-vec embeddings)    │
│  Scoring (0.6 semantic + 0.2 eff + 0.2 │
│           profile)                      │
│  Feedback (EMA α=0.3)                  │
│  Scout (HTTP → external registries)     │
├─────────────────────────────────────────┤
│  Storage: ~/.local/share/skill-curator/ │
│  curator.db (SQLite WAL)                │
└─────────────────────────────────────────┘
         ↕ MCP (StreamableHTTP)
┌─────────────────────────────────────────┐
│          Kiro CLI (agent)               │
│  Steering: "call skill_match before     │
│             every task"                 │
│  Hook startup: skill_reindex()          │
│  Hook shutdown: skill_gaps()            │
└─────────────────────────────────────────┘
```

## Stack

- Python 3.11+
- FastMCP (mcp SDK)
- sqlite-vec (embeddings)
- sentence-transformers (MiniLM-L6-v2 or paraphrase-multilingual-MiniLM-L12-v2)
- httpx (scout HTTP calls)
- uv (package management)

## Schema

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
    profile_tags TEXT,  -- JSON array
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
    embedding float[384]
);
```

## Scoring Formula

```
score_final = 0.6 * cosine_similarity + 0.2 * effectiveness + 0.2 * profile_match
```

- `cosine_similarity`: embedding(task) vs embedding(skill.description + skill.trigger)
- `effectiveness`: EMA score (0.0-1.0, default 0.5, α=0.3)
- `profile_match`: 1.0 if skill in profile.expected_skills, else 0.0

## Lifecycle Transitions

```
draft → active (skill_promote or effectiveness > 0.7 after 3+ uses)
active → stale (no use in 30 days)
stale → active (used again)
stale → archived (no use in 90 days, or effectiveness < 0.3)
archived → active (skill_promote)
```

## Scout Sources (MVP)

1. skills-manager marketplace (skills.sh) via HTTP API
2. GitHub search: `topic:claude-code-skills` OR `topic:agent-skills`
3. Anthropic official: github.com/anthropics/skills

## Integration

- **Transport**: StreamableHTTP on port 3204
- **Systemd**: `~/.config/systemd/user/skill-curator.service`
- **Skills dir**: reads `~/.kiro/skills/**/*.md` + `~/.kiro/skills/auto-generated/**/*.md`
- **Migration**: imports existing `.usage.json` data on first `skill_reindex()`

## Development

```bash
cd ~/git/skill-curator-mcp
uv venv .venv
uv pip install -e ".[dev]"
pytest
```

## License

Apache-2.0
