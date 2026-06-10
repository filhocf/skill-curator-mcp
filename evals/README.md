# Eval Framework — Baseline de Accuracy do Agente

Mede se o subagent reproduz PRs reais quando recebe apenas a descrição do problema.

## Processo
1. Checkout do commit ANTES do fix
2. Worker recebe ISSUE.md como prompt
3. Worker implementa
4. Comparar com EXPECTED.md
5. Classificar: ✅ equivalente | ⚠️ parcial | ❌ falhou

## Resultados
| # | Eval | Worker | Resultado | Data |
|---|------|--------|-----------|------|
| 001 | cosine-fix | (pendente) | | |
