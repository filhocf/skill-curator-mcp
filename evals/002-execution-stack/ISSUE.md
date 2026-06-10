# Feature: get_execution_stack tool

## Descrição
Preciso de uma tool MCP no task-orchestrator-py que mostre o "stack de execução" — quais items estão em andamento (work) ou suspensos (blocked/hold) em ordem de profundidade.

## Motivação
Quando o agente é interrompido por laterais, perde noção de "onde estava". Esta tool permite ver o stack a qualquer momento.

## Comportamento esperado
- Retorna lista de "frames" ordenados por profundidade (deepest = lateral mais recente)
- Frame = item em status `work` (ativo) ou `blocked` (suspenso por hold)
- Cada frame inclui: depth, item_id, title, status, active (bool), execution_state (nota se existir)
- Items em `queue`, `done`, `cancelled` NÃO aparecem no stack
- Workspace filter opcional

## Exemplo de retorno
```json
[
  {"depth": 0, "item_id": "abc", "title": "Deploy feature", "status": "blocked", "active": false, "execution_state": {"last_action":"editing handler"}},
  {"depth": 1, "item_id": "def", "title": "Responder pergunta", "status": "work", "active": true, "execution_state": null}
]
```

## Arquivos relevantes
- src/task_orchestrator/engine.py (lógica de negócio)
- src/task_orchestrator/server.py (registro de tools MCP)
- src/task_orchestrator/db.py (queries SQL)

## Requisitos
- Incluir nota com key "execution-state" no frame se existir
- Profundidade calculada via parent_id (recursivo)
- Se workspace fornecido, filtrar items por tags do workspace
