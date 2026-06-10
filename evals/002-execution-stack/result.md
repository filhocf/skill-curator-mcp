# Eval 002 — Resultado

**Data**: 2026-06-10
**Worker**: subagent (coder)
**Classificação**: ✅ Equivalente

## Critérios de sucesso

| Critério | Resultado |
|----------|-----------|
| Função em engine.py (query work/blocked) | ✅ |
| Calcula profundidade via parent_id | ✅ |
| Inclui nota execution-state | ✅ |
| Ordena por depth | ✅ |
| Workspace filter | ✅ |
| Tool registrada em server.py com @mcp.tool() | ✅ |
| Docstring clara | ✅ |
| Testes (mínimo 3) | ✅ (5 testes) |

## Análise

Worker reproduziu 100% da feature no first-try com 5 testes (nós fizemos 6). A issue era mais detalhada que a 001 (incluía exemplo de output, requisitos claros), o que confirma: **nível de detalhe da issue correlaciona com accuracy**.

## Comparação com Eval 001

| Eval | Issue detail | Accuracy |
|------|:---:|:---:|
| 001 (bug fix) | Média (sem exemplo de output esperado) | 60% |
| 002 (feature) | Alta (com JSON exemplo + requisitos) | 100% |

## Conclusão

Features bem-especificadas com exemplos de output → worker acerta first-try.
Bugs com descrição genérica → worker acerta root cause mas perde edge cases.
