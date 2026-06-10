# Feature: get_onboarding_guide tool

## Descrição
Preciso que o skill-curator-mcp seja auto-descritivo — qualquer agente que conecte deve saber como usar as tools sem depender de documentação externa.

## O que implementar
Uma tool `get_onboarding_guide()` que retorna um dict com:
- Propósito do MCP (1 frase)
- Quick start (passos ordenados de uso)
- Lista de tools com descrição curta de cada uma
- Protocolo recomendado (startup, before_task, after_task, shutdown)
- Notas importantes (thresholds, comportamentos)

## Onde
- Função em src/skill_curator/tools.py
- Registrar como @mcp.tool() em src/skill_curator/server.py
- Adicionar `instructions` param no construtor FastMCP (resumo de 1 linha)

## Teste
Verificar que retorna dict com keys esperadas e que o count de tools está correto.
