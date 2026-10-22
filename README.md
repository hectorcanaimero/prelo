# Prelo

> *No prelo*: a punto de publicarse.

Mesa editorial de agentes: convierte **una idea** en un post para el blog en tres idiomas
(es · pt · en) y en derivados para LinkedIn e Instagram, con **aprobación humana** antes de publicar.

```
START → investigar → redigir → revisar ─┬─ ok ─────► aprovar (interrupt) ─┬─ aprovado ─► publicar → END
                         ▲              └─ violação ─┐                     ├─ editar ───► redigir
                         └───────────────────────────┘                     └─ descartar ─► END
```

- **LangGraph**: el flujo es un `StateGraph`; la aprobación usa `interrupt()` y un checkpointer, así un post
  puede esperar días una respuesta sin perder estado.
- **Revisión de marca determinista**: reglas en `marca.toml` (más `marca.local.toml`, fuera de git).
  Un texto con bloqueos se reescribe solo y nunca se puede aprobar tal cual.
- **Git como CMS**: el blog es Astro estático; Prelo abre un PR con los MDX y el merge es la aprobación.

## Estado

| Versión | Contenido | Estado |
|---------|-----------|--------|
| v0 | Grafo con aprobación, revisión de marca, tests, CI | ✅ |
| v1 | LinkedIn de punta a punta, aprobación en Slack, Langfuse, evals de estilo | ⏳ |
| v2 | Blog como pieza madre (MDX es/pt/en + PR) | |
| v3 | Carruseles e Instagram | |
| v4 | Métricas, servidor MCP, AWS + Terraform | |

## Stack

LangGraph · LangChain · Claude · Postgres + pgvector · FastAPI · Slack (Bolt) · Langfuse · evals en CI ·
MCP · Docker · AWS + Terraform

## Uso

```bash
uv sync
uv run pytest
```

## Documentación

- [PRD](docs/prd/001-prelo.md)
- [Arquitectura y decisiones](docs/arch/001-arquitectura.md)
