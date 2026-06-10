# Eval 001 — Resultado

**Data**: 2026-06-10
**Worker**: subagent (coder)
**Classificação**: ⚠️ Parcial

## Causa raiz identificada pelo worker
✅ Correto — sqlite-vec default é L2, não cosine. Distâncias >1.0 zeravam similarity.

## Critérios de sucesso

| Critério | Resultado |
|----------|-----------|
| Identifica L2 vs cosine | ✅ |
| Altera schema para distance_metric=cosine | ✅ |
| Ajusta cálculo similarity no tools.py | ❌ (não abordou — `1-distance` funciona para vetores normalizados mas não é robusto) |
| Garante embed coverage (fallback indexer) | ❌ (não abordou) |

## Análise

Worker acertou root cause e fix principal em 1 linha. Resultado funcional (testes passam, scores diferenciados). Não cobriu os fixes secundários:
- Cosine distance range 0-2 (com vetores não-normalizados, `1-distance` pode dar negativo)
- 31/66 skills sem embedding (indexer sem fallback)

## Conclusão

Accuracy: **~60%** dos critérios atendidos, mas fix principal correto. O worker resolve o bug reportado mas não antecipa edge cases. Necessário: issue mais detalhada OU reviewer como 2ª passada.
