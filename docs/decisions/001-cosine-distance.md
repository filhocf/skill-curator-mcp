# ADR 001: Cosine Distance para Embeddings

## Status
Aceito (2026-06-10)

## Problema
`skill_match` retornava score 0.1 para TODAS as skills — sem diferenciação.

## Causa Raiz
1. **sqlite-vec default é L2 (euclidean)** — a tabela `skill_embeddings` foi criada sem `distance_metric=cosine`. Com L2, distâncias entre embeddings normalizados ficam >1.0 (ex: 1.14, 1.17). O código fazia `max(0, 1-distance)` → similarity=0 para tudo.
2. **31/66 skills sem embedding** — skills sem `description` nem `trigger_text` geravam embed_text vazio e eram puladas.
3. **Score colapsava para 0.1** — `0.6*0 + 0.2*0.5 + 0.2*0 = 0.1` (similarity zero, effectiveness default 0.5).

## Fix Aplicado
1. **db.py**: Tabela vec0 agora usa `distance_metric=cosine`. Migração automática: detecta schema antigo, dropa e recria.
2. **indexer.py**: Fallback para embed_text — se skill não tem description/trigger, usa `filename + primeira linha do body`.
3. **tools.py**: Similarity = `1.0 - distance/2.0` (cosine distance range 0.0-2.0 → similarity 0.0-1.0).

## Resultado
- 66/66 skills indexadas (antes: 31)
- Distances diferenciadas: 0.51-0.78 para query relevante
- Scores >0.6 para skills relevantes (antes: 0.1 para tudo)

## Lições
- sqlite-vec default é L2, NÃO cosine. Sempre especificar `distance_metric=cosine` para embeddings de modelos sentence-transformers (que produzem vetores normalizados).
- Cosine distance range é 0.0-2.0 (não 0.0-1.0). Similarity = 1 - dist/2.
- Sempre testar com vetores conhecidos que o score diferencia relevante de irrelevante.
