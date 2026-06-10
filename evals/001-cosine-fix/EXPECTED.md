# Fix esperado (referência)

## Root cause
sqlite-vec default é L2 (euclidean), não cosine. Distâncias >1.0 zeravam similarity.

## Correções necessárias
1. db.py: adicionar `distance_metric=cosine` na criação da tabela vec0
2. tools.py: similarity = 1.0 - distance/2.0 (cosine range 0-2)
3. indexer.py: garantir que todas as skills geram embedding (fallback para nome+body)

## Critérios de sucesso
- [ ] Identifica que o problema é L2 vs cosine
- [ ] Altera schema da tabela para distance_metric=cosine
- [ ] Ajusta cálculo de similarity no tools.py
- [ ] Após fix, scores são diferenciados (>0.3 para relevantes)
