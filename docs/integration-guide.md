# Integration Guide — skill-curator-mcp

## Overview

The skill-curator creates a **learning loop** for AI agents: match skills to tasks, follow them, report outcomes, and improve over time. This guide explains the complete integration cycle.

## The 5-Step Cycle

### 1. Startup: `skill_reindex()`

Call at session start to sync the in-memory index with the filesystem.

```python
skill_reindex()
# Returns: {"indexed": 39}
```

This picks up new skills, removes deleted ones, and regenerates embeddings for modified files.

### 2. Each Task: `skill_match(task)`

Before implementing any task, find relevant skills:

```python
skill_match(task="deploy RER to kubernetes DEV cluster")
# Returns: [{"name": "rer-k8s-deploy", "score": 0.63, "description": "..."}]
```

**Decision threshold**: score > 0.5 → read and follow the skill. Score < 0.5 → proceed without.

The score formula: `0.6 * semantic_similarity + 0.2 * effectiveness + 0.2 * profile_match`

### 3. Post-Task: `skill_feedback(name, outcome)`

After using a skill, record the result:

```python
# Skill was helpful and correct
skill_feedback(name="rer-k8s-deploy", outcome="success", task_description="deployed core to dev-rer namespace")

# Skill existed but was incomplete/wrong
skill_feedback(name="rer-k8s-deploy", outcome="failure", task_description="missing step for cert-manager setup")
```

**Outcomes**: `success`, `partial`, `failure`

This updates the effectiveness score via EMA (α=0.3). After 3+ uses with consistent success, effectiveness rises above 0.7 and the skill gets priority in future matching.

### 4. Shutdown: `skill_gaps()`

At session end, detect unmatched patterns:

```python
skill_gaps()
# Returns: [{"task_pattern": "herdr pane management", "gap_count": 3, "suggested_name": "herdr-integration"}]
```

Gaps with count ≥ 3 are candidates for new skills.

### 5. Weekly: `skill_lifecycle()`

Review the overall health of the skill library:

```python
skill_lifecycle()
# Returns: {
#   "promote_candidates": [...],   # draft skills ready for active
#   "archive_candidates": [...],   # stale/ineffective skills
#   "active_count": 25,
#   "stale_count": 3
# }
```

Use `skill_promote(name)` and `skill_archive(name)` to act on candidates.

## System Prompt Template

Add this to your agent's system prompt for automatic integration:

```markdown
## Skills (OBRIGATÓRIO)
Before implementing any task, call `skill_match(task="summary of the task")`.
If score > 0.5: read the skill file and follow it.
After using a skill: `skill_feedback(name="skill-name", outcome="success|failure", task_description="what happened")`.
```

## Why Feedback Matters

Without feedback:
- All skills have effectiveness = 0.5 (default)
- Matching is purely semantic (good skills rank same as bad ones)
- Stale detection doesn't work (no usage data)

With feedback:
- Effective skills bubble up (effectiveness > 0.7 → bonus in ranking)
- Bad skills sink (effectiveness < 0.3 → archive candidate)
- Learning loop: each session makes matching better

## Lifecycle Transitions

```
draft → active       (skill_promote OR effectiveness > 0.7 after 3+ uses)
active → stale       (no use in 30 days)
stale → active       (used again)
stale → archived     (no use in 90 days OR effectiveness < 0.3)
archived → active    (skill_promote)
```
