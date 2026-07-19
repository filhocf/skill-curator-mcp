"""Skill quality auditing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class QualityReport:
    name: str
    path: str
    score: float
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


_PENALTIES = {
    "no_frontmatter": 0.3,
    "no_description": 0.2,
    "no_trigger": 0.15,
    "generic_description": 0.15,
    "too_short": 0.2,
    "too_long": 0.1,
}

_SUGGESTIONS = {
    "no_frontmatter": "Adicione frontmatter YAML com description e trigger no início do arquivo.",
    "no_description": "Adicione o campo 'description' no frontmatter com uma descrição clara da skill.",
    "no_trigger": "Adicione o campo 'trigger' no frontmatter indicando quando a skill deve ser ativada.",
    "generic_description": "Reescreva a descrição para ser específica — evite iniciar com 'Skill:'.",
    "too_short": "Expanda o corpo da skill com mais detalhes, exemplos ou passos.",
    "too_long": "Reduza o corpo da skill removendo conteúdo redundante ou dividindo em skills menores.",
}


def _effective_body_len(body: str) -> int:
    """Compute effective body length excluding structural elements."""
    lines = []
    in_fm = False
    for line in body.splitlines():
        s = line.strip()
        if s == "---":
            in_fm = not in_fm
            continue
        if in_fm:
            continue
        if not s:
            continue
        if s.startswith("#"):
            continue
        lines.append(line)
    return len("\n".join(lines))


def audit_skill(path: Path) -> QualityReport:
    """Audit a single skill file and return a QualityReport."""
    content = path.read_text(encoding="utf-8")
    issues: list[str] = []
    suggestions: list[str] = []

    # Parse frontmatter
    fm_match = re.match(r"^---\n(.+?)\n---\n?", content, re.DOTALL)
    frontmatter: dict[str, str] = {}
    body = content

    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                frontmatter[key.strip()] = val.strip().strip('"').strip("'")
        body = content[fm_match.end() :]
    else:
        issues.append("no_frontmatter")

    if not frontmatter.get("description"):
        issues.append("no_description")
    if not frontmatter.get("trigger"):
        issues.append("no_trigger")

    desc = frontmatter.get("description", "")
    if desc.startswith("Skill:"):
        issues.append("generic_description")

    body_len = _effective_body_len(body)
    if body_len < 100:
        issues.append("too_short")
    if body_len > 5000:
        issues.append("too_long")

    # Score
    score = 1.0
    for issue in issues:
        score -= _PENALTIES[issue]

    # Bonuses (check full body for keyword presence)
    if "Quando usar" in body or "When to use" in body:
        score += 0.1
    if "Steps" in body or "Procedimento" in body or "## Passos" in body:
        score += 0.1

    score = max(0.0, min(1.0, score))

    for issue in issues:
        suggestions.append(_SUGGESTIONS[issue])

    return QualityReport(
        name=path.stem,
        path=str(path),
        score=round(score, 2),
        issues=issues,
        suggestions=suggestions,
    )


def audit_all(skills_dir: Path) -> list[QualityReport]:
    """Audit all .md files in a directory, sorted by score ascending."""
    reports = [audit_skill(p) for p in sorted(skills_dir.glob("*.md"))]
    reports.sort(key=lambda r: r.score)
    return reports
