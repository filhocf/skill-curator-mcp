# Instruções para Worker — Skill Curator MCP

## Estrutura do Projeto

```
src/skill_curator/
├── __init__.py       # version, package exports
├── server.py         # FastMCP app + 8 tool registrations
├── db.py             # SQLite connection, migrations, queries
├── indexer.py        # Filesystem scan, embedding generation
├── scoring.py        # Cosine similarity + composite score
├── scout.py          # httpx client for external sources
└── models.py         # Dataclasses: Skill, Feedback, Gap, ScoutResult
```

## Convenções

- **Async**: todas as tools são `async def`. Use `aiosqlite` para DB.
- **Type hints**: obrigatório em todos os parâmetros e retornos.
- **Docstrings**: Google-style, 1 linha summary + args se necessário.
- **Imports**: stdlib → third-party → local, separados por blank line.
- **Erros**: raise exceções tipadas, FastMCP converte para error response.
- **Logging**: `logging.getLogger(__name__)`, nível INFO para tools, DEBUG para internals.

## Como Rodar

```bash
cd ~/git/skill-curator-mcp
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest                    # unit tests
pytest --cov              # com coverage
python -m skill_curator   # start server (porta 3204)
```

## Ordem de Implementação

1. `models.py` — dataclasses puras, sem dependências
2. `db.py` — conexão + CREATE TABLE + migrations
3. `indexer.py` — scan filesystem + gerar embeddings
4. `scoring.py` — cosine via sqlite-vec + score composto
5. `server.py` — registrar tools no FastMCP, wiring dos módulos
6. `scout.py` — HTTP client (pode ser stub no MVP)
7. Testes de integração (skill_match end-to-end)

## Limites

- **NÃO** modificar `README.md` nem `pyproject.toml`.
- **NÃO** instalar dependências extras sem aprovação do orquestrador.
- **NÃO** criar arquivos fora de `src/skill_curator/` e `tests/`.
- **NÃO** usar global state — passar db connection via injeção.
- Manter cada módulo < 200 linhas. Se passar, propor split.
