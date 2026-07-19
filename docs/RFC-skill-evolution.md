# RFC: Skill Evolution — Auto-Correction Loop

**Author**: filhocf
**Date**: 2026-07-03
**Status**: Draft
**Repo**: filhocf/skill-curator-mcp

---

## Problem

The skill-curator tracks **effectiveness** via EMA scoring, but when a skill is wrong or incomplete, nothing corrects the content. The feedback loop is:

```
match → use → fail → score drops → skill ranks lower
```

This means bad skills get RANKED lower but never FIXED. The agent repeats the same failure path next time a different task matches the same skill. The fix stays in memory (memory_store) but never reaches the skill file.

## Desired State

```
match → use → fail → diagnose what's wrong → evolve skill → reindex → next match uses FIXED version
```

## Prior Art

| System | Mechanism | Limitation |
|--------|-----------|-----------|
| Hermes (T'Pol) | `skill_evolve` native — rewrites on failure | Opaque, no versioning |
| Karpathy Auto-Research | edit → experiment → measure → iterate | Research context, not skills |
| HyperAgents (Meta/UBC) | Metacognitive self-modification | Academic, not productized |
| Addy Osmani | Compound learning via AGENTS.md | Manual, not automated |
| Our memory_harvest | Extracts learnings post-session | Saves to memory, not to skill files |
| Our mistake_note_add | Records error patterns | Available for avoidance, not correction |

## Proposal: `skill_evolve` Tool

### Interface

```python
skill_evolve(
    name: str,              # skill name (e.g. "sonarqube")
    correction: str,        # what to change (natural language)
    task_description: str,  # context of what was being done
    section: str = None,    # optional: which section to target
    dry_run: bool = True    # preview changes without writing
)
```

### Behavior

1. **Read** current skill content from filesystem
2. **Identify** the section to modify (by `section` param or heuristic from `correction`)
3. **Generate** updated content preserving structure (headings, format, existing correct info)
4. **Version** the original: write `.versions/{name}.{timestamp}.md` before overwriting
5. **Write** updated skill to filesystem
6. **Reindex** embeddings for the modified skill
7. **Log** the evolution event (who, when, what changed, why)
8. **Update** effectiveness: reset to 0.5 (neutral) after evolution — force re-evaluation

### Safety Guards

| Guard | Mechanism |
|-------|-----------|
| Dry run by default | `dry_run=True` — preview diff without writing |
| Version preservation | Original saved in `.versions/` before overwrite |
| Minimum uses before evolve | Require ≥2 failures before allowing evolve (avoid knee-jerk) |
| Human approval option | Config: `skill_evolve_auto_approve = false` → requires user OK |
| Scope limitation | Only modifies the targeted section, not the entire file |
| Rollback | `skill_rollback(name, version)` restores from `.versions/` |

### When to Trigger

The agent should call `skill_evolve` when ALL of these are true:
1. A skill was matched and followed (skill_match score > 0.5)
2. The outcome was failure (skill_feedback outcome="failure")
3. The agent knows WHAT was wrong (can articulate the correction)
4. The failure is in the skill content (not in external systems)

Add to system prompt:
```
If a skill was wrong/incomplete AND you know the fix:
  skill_evolve(name="skill", correction="what to change", task_description="context", dry_run=False)
This rewrites the skill so next time it's correct.
```

## Data Model

### Evolution Log (new table: `skill_evolutions`)

```sql
CREATE TABLE skill_evolutions (
    id INTEGER PRIMARY KEY,
    skill_name TEXT NOT NULL,
    evolved_at TEXT NOT NULL,  -- ISO 8601
    correction TEXT NOT NULL,
    task_description TEXT,
    section_modified TEXT,
    diff_summary TEXT,         -- human-readable diff
    previous_version TEXT,     -- path to .versions/ file
    triggered_by TEXT          -- "agent" | "manual"
);
```

### Versioning Directory

```
~/.kiro/skills/
├── sonarqube.md              ← current (evolved)
├── .versions/
│   ├── sonarqube.2026-07-03T15:30:00.md  ← before evolution
│   └── sonarqube.2026-06-15T10:00:00.md  ← older version
```

## Integration with Existing Tools

| Existing Tool | How it connects |
|---------------|----------------|
| `skill_feedback(failure)` | Decreases effectiveness. After 2+ failures on same skill → suggest evolve |
| `skill_match` | Returns evolved skill on next match (reindex picks it up) |
| `skill_reindex` | Called automatically after evolve |
| `skill_lifecycle` | Evolution count visible in lifecycle report |
| `skill_audit` | Checks if evolved skills have degraded quality |
| `skill_rollback(name, version)` | NEW — restores from .versions/ |

## Implementation Plan

| Phase | What | Effort |
|-------|------|--------|
| 1 | `skill_evolve` tool (dry_run only) | 2h |
| 2 | Versioning (.versions/ dir + write) | 1h |
| 3 | `skill_evolutions` table + logging | 1h |
| 4 | `skill_rollback` tool | 30min |
| 5 | System prompt integration + docs | 30min |
| 6 | Tests (unit + integration) | 2h |

**Total**: ~7h implementation.

## Open Questions

1. **Who generates the corrected content?** The calling agent (Kiro) rewrites inline? Or skill_evolve uses a local LLM (Ollama) to rewrite?
   - **Proposed**: Agent provides `correction` in natural language. The tool applies it as a patch (string replacement or section rewrite). No LLM inside the tool.

2. **Approval gate**: Should evolved skills require human approval before being active?
   - **Proposed**: Config flag `skill_evolve_auto_approve`. Default `true` for our use (we trust ourselves). Can be set to `false` for shared environments.

3. **Effectiveness reset**: After evolution, should effectiveness reset to 0.5 or keep the history?
   - **Proposed**: Reset to 0.5. The evolved skill is essentially new content and needs to prove itself again.

## References

- [Self-Improving Coding Agents (Addy Osmani)](https://addyosmani.com/blog/self-improving-agents/)
- [HyperAgents (Meta/UBC)](https://arxiv.org/abs/2505.22954)
- [Plano Self-Improvement](~/git/conhecimentos-de-ia/harness/plano-self-improvement-agente.md)
- [Integration Guide](~/git/skill-curator-mcp/docs/integration-guide.md)
- [Padrão Hierarquia Enforcement](~/git/conhecimentos-de-ia/harness/padrao-hierarquia-enforcement.md)
