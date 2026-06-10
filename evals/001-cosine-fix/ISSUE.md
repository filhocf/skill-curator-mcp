# Bug: skill_match retorna score 0.1 para todas as skills

## Descrição
A tool `skill_match` retorna score 0.1 para TODAS as skills, independente da query. Não diferencia skills relevantes de irrelevantes.

## Reprodução
1. Chamar `skill_match(task="deploy Spring Boot Kubernetes", top_k=5)`
2. Todas as skills retornam score=0.1
3. Esperado: skills como jenkins-pipeline e rer-k8s-deploy deveriam ter score > 0.5

## Contexto técnico
- Embeddings são gerados via sentence-transformers (MiniLM)
- Armazenados em sqlite-vec (tabela vec0)
- Scoring: 0.6*similarity + 0.2*effectiveness + 0.2*profile_match
- effectiveness default = 0.5

## Arquivos relevantes
- src/skill_curator/db.py (schema + search_similar)
- src/skill_curator/tools.py (skill_match)
- src/skill_curator/indexer.py (reindex_all)
