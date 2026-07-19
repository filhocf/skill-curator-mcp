# Gap Analysis: DEVELOPMENT-STANDARDS vs Estado da Arte Dev Agêntico 2026

**Data**: 2026-07-19
**Contexto**: Pesquisa sobre boas práticas consolidadas de desenvolvimento agêntico em 2026 para verificar alinhamento do nosso fluxo.

## Cenário 2026 — O que consolidou

A indústria convergiu para **Spec-Driven Development (SDD)** como metodologia dominante. Fluxo canônico:

```
Specify → Plan → Tasks → Implement → Verify
```

### Ferramentas/Padrões-chave

| Padrão | O que é | Adoção |
|--------|---------|--------|
| **AGENTS.md** | Arquivo raiz com instruções para agentes (Linux Foundation/AAIF) | 60K+ repos, padrão aberto |
| **Kiro `/spec`** | Requirements → Design → Tasks → Execution com verificação | Built-in Kiro v3 |
| **GitHub Spec Kit** | CLI model-agnostic SDD (/constitution, /specify, /plan, /tasks) | Referência open source |
| **EARS notation** | 5 patterns para specs AI-parseable | Padrão emergente para acceptance criteria |
| **JiTTesting** | Testes efêmeros gerados por PR, descartados após merge (Meta) | Experimental |
| **Verification Loops** | Agente verifica próprio output (TDD como instância) | Universal |
| **Fresh Context Pattern** | Nova instância por task, estado em git/files | Power users |

### 15 Metodologias Mapeadas (pirâmide)

1. **Orchestration**: BMAD (multi-agent governance), GSD (6-phase meta-prompting)
2. **Specification**: SDD, Doc-Driven, Req-Driven, DDD
3. **Behavior**: BDD (Given-When-Then), ATDD (acceptance first), CDD (contracts)
4. **Delivery**: FDD (feature-by-feature), Context Engineering
5. **Implementation**: TDD (Red-Green-Refactor), Eval-Driven, Multi-Agent
6. **Optimization**: Iterative Loops, Fresh Context, Prompt Engineering

### EARS Notation (5 patterns)

```
Ubiquitous:    "The system SHALL [behavior]"
Event-driven:  "WHEN [trigger] THE [system] SHALL [response]"
State-driven:  "WHILE [state] THE [system] SHALL [behavior]"
Unwanted:      "IF [condition] THEN THE [system] SHALL [response]"
Optional:      "WHERE [feature] THE [system] SHALL [behavior]"
```

## Nosso Fluxo Atual (§8 DEVELOPMENT-STANDARDS)

```
G0 Thinking (arch-analyst) → G1 Plan Review → G2 Spec → G3 RED (dev-tests) → G4 GREEN (dev-*) → G5 Review → G6 Push
```

## Comparativo

| Aspecto | Estado da Arte | Nós | Status |
|---------|---------------|-----|--------|
| AGENTS.md | Padrão universal, 8 seções | ✅ Em todos os repos | ALINHADO |
| Spec como artefato versionado | specs/{spec,plan,tasks}.md no repo | ✅ specs/planned + implemented | ALINHADO |
| Spec ANTES de código | Obrigatório (4 fases) | ✅ G0→G1→G2 antes de implementar | ALINHADO |
| TDD separação writer/tester | Recomendado mas não universal | ✅ dev-tests ≠ dev-* | ACIMA |
| Multi-Agent delegation | Tier 5 (orquestrador + workers) | ✅ arch + dev-tests + dev-* + reviewer | ACIMA |
| Verification Loops | Auto-verificação do agente | ✅ Review loop NEEDS_CHANGES | ALINHADO |
| Constitution/Guardrails | Documento imutável projeto-wide | ✅ GUARDRAILS.md por projeto | ALINHADO |
| EARS notation | Specs AI-parseable | ❌ Specs em prosa livre | **GAP** |
| Kiro `/spec` nativo | Requirements→Design→Tasks automático | ⚠️ Fluxo equivalente mas manual | OPORTUNIDADE |
| JiTTesting | Testes efêmeros por PR | ❌ Só TDD persistente | GAP menor |
| Fresh Context Pattern | Estado em files, instância fresca | ✅ active-tasks/ + memory | ALINHADO |
| Context Engineering | Design intencional do contexto | ✅ Skills, steerings, memory_context | ACIMA |
| SKILL.md (Anthropic) | Task-scoped capability | ✅ ~/.kiro/skills/ formato similar | ALINHADO |
| Eval-Driven Development | Evals formais para agent output | ❌ Sem evals | **GAP** |
| Permission Tiers (✅/⚠️/🚫) | Seção no AGENTS.md | ✅ pre-enforcement hooks | ACIMA |

## 5 Gaps Identificados

### GAP 1: EARS Notation nas Specs — PRIORIDADE ALTA

**Problema**: Specs em prosa livre → ambiguidade → agente implementa com interpretação variável.

**Solução**: Adotar EARS nos 5 patterns para acceptance criteria em specs novas.

**Esforço**: Baixo (template + disciplina). Alto impacto.

### GAP 2: Eval-Driven Development — PRIORIDADE MÉDIA

**Problema**: Não medimos qualidade do output dos agents. Não sabemos se harness melhora ou degrada.

**Solução**: Evals para:
- Aderência worker→spec (LLM-as-judge)
- Qualidade de testes (dev-tests)
- Custo/benefício por sessão

**Esforço**: Alto. Requer infra de evals.

### GAP 3: JiTTesting (Testes Efêmeros por PR) — PRIORIDADE BAIXA

**Problema**: TDD cobre happy path + edge cases pré-definidos. Mutações do diff não são testadas.

**Solução**: No review loop: "gere 5 testes que tentam QUEBRAR este diff".

**Esforço**: Baixo (prompt pro reviewer). Ganho incremental.

### GAP 4: `/spec` nativo Kiro v3 — DECISÃO PENDENTE

**Problema**: Fazemos o mesmo fluxo manualmente (subagents). Kiro v3 oferece automatizado.

**Solução**: Testar `/spec new` em feature real. Avaliar se substitui G0+G1+G2.

**Decisão**: Se output bom → adotar (menos fricção). Se ruim → manter (mais robusto).

### GAP 5: Constitution unificada — COSMÉTICO

**Problema**: Regras espalhadas (AGENTS.md + GUARDRAILS.md + DEVELOPMENT-STANDARDS).

**Solução**: Não criar mais arquivo. Garantir seção "Constraints" com EARS no AGENTS.md.

## Fontes

- [AGENTS.md Complete Guide 2026](https://codersera.com/blog/agents-md-complete-guide-2026/) — Linux Foundation
- [AGENTS.md vs CLAUDE.md vs Cursor Rules](https://codersera.com/blog/agents-md-vs-claude-md-vs-cursor-rules-comparison-2026/)
- [SDD Definitive 2026 Guide](https://thebcms.com/blog/spec-driven-development) — BCMS
- [15 Methodologies Reference](https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/main/guide/core/methodologies.md)
- [Kiro CLI v3 Specs](https://kiro.dev/docs/cli/v3/specs/)
- [Spec-Driven Development with AI Agents](https://www.augmentcode.com/guides/ai-coding-agents-for-spec-driven-development-automation) — Augment
- [JiTTesting at Meta](https://arxiv.org/abs/2601.22832) — Harman 2026
- ETH Zurich: LLM-generated AGENTS.md lowered success by 3% vs human-written (arXiv 2602.11988)

## Veredicto

**Nosso fluxo está FORTE e ACIMA DA MÉDIA.** Gaps reais:
1. EARS nas specs (fácil, alto impacto)
2. Evals (mais trabalho, necessário para medir)

O resto é otimização incremental ou decisão de conveniência.
