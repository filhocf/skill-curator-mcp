# Eval 002 — Referência (fix real)

## O que fizemos
Adicionamos `get_execution_stack` em engine.py + server.py do task-orchestrator-py.

## Critérios de sucesso
- [ ] Função em engine.py que query items com status work/blocked
- [ ] Calcula profundidade via parent_id
- [ ] Inclui nota execution-state se existir
- [ ] Ordena: frames suspensos por depth, frame ativo por último
- [ ] Workspace filter funcional
- [ ] Tool registrada em server.py com @mcp.tool()
- [ ] Docstring clara (explica uso para interrupt/resume)
- [ ] Testes unitários (pelo menos 3)
