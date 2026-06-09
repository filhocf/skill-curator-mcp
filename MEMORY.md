# Memory — Skill Curator MCP

## Estado Atual

- **Criado em**: 2026-06-09
- **Status**: scaffold criado, 0/8 tools implementadas
- **Próximo passo**: implementar `models.py` → `db.py` → `indexer.py`

## Decisões Tomadas

- FastMCP (SDK oficial MCP) como framework
- sqlite-vec para embeddings (single-file, sem infra extra)
- MiniLM-L6-v2 (384 dims) como modelo de embedding
- Separado do memory-service (responsabilidades distintas)
- Porta 3204 (StreamableHTTP)
- EMA α=0.3 para feedback scoring
- Score: 0.6 semantic + 0.2 effectiveness + 0.2 profile_match
- Skills dir: `~/.kiro/skills/**/*.md`
- Storage: `~/.local/share/skill-curator/curator.db` (WAL mode)

## Histórico

| Data | Evento |
|------|--------|
| 2026-06-09 | Projeto criado. README + scaffold + docs gerados. |
