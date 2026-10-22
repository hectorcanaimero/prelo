# Arquitectura 001 · Prelo

## Vista general

```
 Slack (aprobación) ◄────────────┐
        │                         │
        ▼                         │
 FastAPI ──► LangGraph (StateGraph) ──► publicadores
              │   checkpointer Postgres      ├─ GitHub: PR en site-guria (blog es/pt/en)
              │                              ├─ LinkedIn API
              │                              └─ Instagram Graph API (+ imágenes en R2)
              ├─ agentes (create_agent)
              │    investigador · redator · tradutor · adaptador · arte
              ├─ revisão de marca (determinista, marca.toml)
              └─ Postgres + pgvector (posts publicados, RAG sobre repos y posts)

 Langfuse ◄── trazas, tokens, costo        GitHub Actions ── tests + evals
```

## Grafo (v0)

```
START → investigar → redigir → revisar ─┬─ ok ─────► aprovar (interrupt) ─┬─ aprovado ─► publicar → END
                         ▲              └─ violação ─┐                     ├─ editar ───► redigir
                         └───────────────────────────┘ (máx. 2 intentos)   └─ descartar ─► END
```

- `revisar` es código, no un LLM: si encuentra un bloqueo, vuelve a `redigir` con las violaciones como feedback.
  Tras 2 intentos fallidos va a `aprovar` igual, con las violaciones visibles, y no se puede aprobar sin editar.
- `aprovar` usa `interrupt()`: el grafo se detiene, el estado queda en el checkpointer y se reanuda con
  `Command(resume={"decisao": ...})` cuando llega la respuesta de Slack o el merge del PR.
- Los nodos reciben sus dependencias (modelo, publicadores) por inyección: los tests usan dobles sin red.

## Decisiones

| # | Decisión | Por qué |
|---|----------|---------|
| D1 | LangGraph en vez de Agno | Agno ya está en otros repos; LangGraph da `interrupt` + checkpointer, que es justo el flujo con aprobación de días. |
| D2 | Git como CMS del blog | El sitio es Astro estático. El PR da revisión, historial y validación del schema en CI sin infraestructura nueva. |
| D3 | Revisión de marca determinista | Un modelo puede saltarse la regla; una regex no. Las reglas viven en `marca.toml`; los nombres reales de empleadores, en `marca.local.toml` (fuera de git), para no publicarlos en el propio repo. |
| D4 | Modelo fuerte para la pieza madre, barato para traducir/adaptar | Baja el costo por post sin bajar la calidad del texto principal. |
| D5 | Texto de carruseles en HTML → PNG (Playwright) | El texto generado dentro de imágenes de IA sale deformado. |
| D6 | Langfuse self-hosted | Open source, costo por agente, y muestra operación de infraestructura propia. |
| D7 | FastAPI propio, no Agent Server | Sin dependencia de licencia; el grafo se usa como librería. |

## Estado del post (`EstadoPost`)

- `tema`, `idioma_base`
- `fontes`: lista de `{url, titulo, trecho}`
- `rascunho`: `{titulo, resumo, corpo}` por idioma
- `violacoes`: resultado de la revisión
- `tentativas`: intentos de redacción
- `decisao`: `aprovado | editar | descartar` + comentario
- `publicacoes`: `{canal, url, data}`

## Seguridad
- Tokens (GitHub, LinkedIn, Instagram, Slack) solo en variables de entorno; nunca en el estado ni en las trazas.
- El contenido de fuentes externas va delimitado en el prompt (riesgo de prompt injection).
- Los publicadores solo corren después de `aprovado`; el nodo lo verifica de nuevo (defensa en profundidad).
