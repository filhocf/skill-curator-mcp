# RFC-SC-06: Scout Ingest & Adapt

**Status**: Draft → Implementando
**Data**: 2026-07-19
**Autor**: Claudio Ferreira Filho / Kiro
**Prioridade**: Alta (desbloqueia evolução de skills a partir de referências externas)
**Depende de**: RFC-SC-01 (scout multi-source)

## Problema

O `skill_scout` encontra skills externas mas retorna apenas metadados (nome, URL, description).
O usuário precisa manualmente: abrir o link → ler → extrair o relevante → adaptar → escrever na skill local.

**Exemplo real**: scout encontrou `sergebulaev/linkedin-skills` (11 skills LinkedIn) e `blacktwist/social-media-skills` (12+ skills). Mas não temos como automaticamente baixar, analisar e propor merge com nossa `personal-branding.md`.

## Requisitos (Prosa + EARS)

### Funcional

**R1**: Quando scout encontra resultados relevantes, poder baixar o conteúdo dos repos.

EARS: WHEN `skill_scout` returns results with relevance >= 0.6
      THE system SHALL be capable of fetching the README and skill files from the source repository.

**R2**: Após baixar, comparar com a skill local mais próxima e identificar gaps.

EARS: WHEN external skill content is fetched
      THE system SHALL compare it with the closest local skill
      AND return a structured diff: sections the external has that we don't.

**R3**: Propor uma evolução concreta (texto) que pode ser aplicada via skill_evolve.

EARS: WHEN comparison identifies gaps in the local skill
      THE system SHALL generate an `evolution_proposal` containing:
      - `target_skill`: local skill to evolve
      - `sections_to_add`: new content from external
      - `adapted_content`: content rewritten for our context (tom, projetos, audiência)
      - `sources`: URLs de onde veio

**R4**: O processo completo deve ser uma tool MCP chamável.

EARS: The system SHALL expose a `skill_scout_ingest` tool that accepts:
      - `source_url`: GitHub repo URL
      - `target_skill`: local skill name to compare/evolve (optional, auto-detect)
      AND returns the evolution_proposal ready for skill_evolve.

**R5**: Nunca aplicar automaticamente — sempre dry_run primeiro.

EARS: The `skill_scout_ingest` tool SHALL always return proposals as dry_run
      AND NEVER modify skill files without explicit user approval via `skill_evolve(dry_run=False)`.

### Não-Funcional

**R6**: Fetch de repo externo deve respeitar rate limits.

EARS: The system SHALL NOT make more than 5 HTTP requests per ingest operation.

**R7**: Conteúdo baixado deve ser cacheado (scout_cache).

EARS: Fetched content SHALL be cached in scout_cache with 7-day TTL.

## Design

### Nova tool: `skill_scout_ingest`

```python
def skill_scout_ingest(
    source_url: str,
    target_skill: str | None = None,
    *,
    db: Database,
    encoder: Any,
    skills_dir: str,
) -> dict:
    """Fetch external skill, compare with local, propose evolution."""
    
    # 1. Fetch repo content (README + skill files)
    content = _fetch_repo_content(source_url)
    
    # 2. Find closest local skill (or use target_skill)
    if not target_skill:
        target_skill = _find_closest_local(content["description"], db, encoder)
    
    # 3. Load local skill content
    local_content = _read_local_skill(target_skill, skills_dir)
    
    # 4. Compare and identify gaps
    gaps = _compare_skills(local_content, content)
    
    # 5. Generate adapted proposal
    proposal = _generate_proposal(gaps, local_content, content)
    
    return {
        "target_skill": target_skill,
        "source": source_url,
        "gaps_found": len(gaps),
        "sections_to_add": gaps,
        "adapted_content": proposal,
        "apply_with": f"skill_evolve(name='{target_skill}', correction=<adapted_content>, dry_run=False)"
    }
```

### `_fetch_repo_content`

```python
def _fetch_repo_content(url: str) -> dict:
    """Fetch README + skill files from GitHub repo."""
    # Parse owner/repo from URL
    # GET /repos/{owner}/{repo}/readme → base64 decode
    # GET /repos/{owner}/{repo}/contents/skills/ → list skill files
    # For each .md file: GET content
    # Return: {"description": ..., "skills": [{"name": ..., "content": ...}]}
```

### `_compare_skills`

Compara seção por seção (headers H2/H3):
- Seções presentes em ambos → skip
- Seções só no externo → gap (candidata a adicionar)
- Seções só no local → keep (nosso contexto)

### `_generate_proposal`

Para cada gap, reescreve adaptando ao contexto local:
- Substitui referências genéricas pelo perfil do Claudio
- Mantém tom direto/técnico
- Remove marketing fluff
- Adiciona links para nossos projetos quando relevante

## Integração com Fluxo Existente

```
skill_scout(query) → encontra repos relevantes
    ↓
skill_scout_ingest(source_url) → baixa, compara, propõe
    ↓
Apresenta proposal ao usuário → aprovação
    ↓
skill_evolve(name, correction=proposal, dry_run=False) → aplica
    ↓
skill_reindex() → atualiza embeddings
```

## Fora de Escopo

- Download de repos inteiros (só README + skill files .md)
- Criação de skill do zero a partir de externa (isso é generate_draft_skill)
- Merge automático sem aprovação
- Suporte a repos privados

## Critérios de Aceite

- [ ] `skill_scout_ingest(source_url)` baixa README do repo
- [ ] Identifica closest local skill automaticamente
- [ ] Compara seção por seção e lista gaps
- [ ] Gera proposal adaptada ao nosso contexto
- [ ] Nunca modifica arquivos (dry_run only)
- [ ] Cache 7d para conteúdo baixado
- [ ] ≤5 HTTP requests por ingest
- [ ] Testes: repo real (mock), comparison, proposal generation
