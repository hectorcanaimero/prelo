# Prelo

Mesa editorial de agentes: a partir de un tema investiga, redacta, revisa la marca y adapta la pieza a LinkedIn. Una
persona la aprueba en Slack y Prelo la agenda y la publica. Nada sale sin esa aprobación.

Canales: blog (es/pt/en, aprobado con el merge del PR en `site-guria`), LinkedIn (pt-BR) e Instagram (carrusel).
Diseño completo en [`docs/arch/001-prelo.md`](docs/arch/001-prelo.md).

## Cómo funciona

```
START → investigar → redigir → revisar ─┬─ ok o 2 reescrituras ─► traduzir → pr_blog ⏸ (merge) → esperar_deploy ⏸
              ▲                         └─ violación (≤2) ─┐                                          │
              └──────────────────────────────────────────┘                                          ▼
   adaptar_linkedin → revisar_linkedin → aprovar ⏸ (Slack) ──aprobado/descartar──► adaptar_carrossel → revisar_carrossel
        ▲                                   │                                             ▲                    │
        └───────────── editar ──────────────┘                                             └── editar ── aprovar_carrossel ⏸ → END
```

- Los derivados se deciden en serie: primero LinkedIn y, al decidirlo, el carrusel. Descartar uno no afecta al otro.
- `⏸` es un `interrupt()` de LangGraph: el post espera en Postgres (`PostgresSaver`) lo que haga falta, `thread_id` = `post_id`.
- La revisión de marca es código determinista (`marca.toml` + `PRELO_BLOQUEIA`). Si tras 2 reescrituras sigue habiendo
  violaciones, Slack no ofrece "Aprobar".
- Aprobar solo se puede con los botones de Slack. La API no tiene ningún endpoint que apruebe.
- Un worker revisa cada minuto las piezas aprobadas, les asigna el siguiente hueco (martes a jueves, una por día) y
  publica al llegar la hora.

Todo corre en un solo proceso (`python -m prelo.app`): la API HTTP (puerto 8000), la app de Slack (Socket Mode) y el
worker de agenda.

## Levantarlo

```bash
cp .env.example .env   # o crea .env a mano con las variables de abajo
docker compose up
```

Levanta Postgres, Langfuse (trazas, http://localhost:3000) y Prelo. Las migraciones se aplican al arrancar.
Comprobación: `curl http://localhost:8000/saude` → `200` si la base responde, `503` si no.

Desarrollo local: `uv sync && uv run pytest`.

## Crear la app de Slack

1. En <https://api.slack.com/apps> → **Create New App** → **From a manifest**, elige el workspace y pega
   [`slack-manifest.yml`](slack-manifest.yml) (Socket Mode, comando `/prelo`, interactividad, scopes `chat:write` y `commands`).
2. **Install to Workspace** y copia el *Bot User OAuth Token* (`xoxb-…`) → `SLACK_BOT_TOKEN`.
3. **Basic Information → App-Level Tokens**: genera uno con el scope `connections:write` (`xapp-…`) → `SLACK_APP_TOKEN`.
4. Invita al bot al canal de aprobación (`/invite @Prelo`) y pon su ID en `SLACK_CANAL`.
5. En Slack: `/prelo <tema>`. Más detalle en [`docs/slack.md`](docs/slack.md).

## Apuntar Hermes a Prelo

Hermes inicia posts con una llamada HTTP:

```bash
curl -X POST http://prelo:8000/posts \
  -H "Authorization: Bearer $PRELO_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tema": "agentes de IA en producción"}'
# 202 {"post_id": "…"}
```

- Sin token o con uno incorrecto → `401`. Tema vacío → `422`.
- La llamada vuelve cuando el post llega a la primera pausa (la pieza ya está pendiente en Slack).
- Desde ahí, la aprobación es solo en Slack.

## Variables de entorno

| Variable | Para qué |
|----------|----------|
| `DATABASE_URL` | Postgres (datos y checkpoints del grafo) |
| `ANTHROPIC_API_KEY` | LLM |
| `TAVILY_API_KEY` | Búsqueda de fuentes |
| `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_CANAL` | App de Slack y canal de aprobación |
| `LINKEDIN_TOKEN`, `LINKEDIN_AUTHOR_URN` | Publicar en LinkedIn |
| `LINKEDIN_TOKEN_EXPIRES_AT` | Fecha ISO de caducidad del token; Prelo avisa en Slack 7 días antes |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Trazas y costos por post |
| `PRELO_API_TOKEN` | Token Bearer que Hermes envía a `POST /posts` |
| `PRELO_BLOQUEIA` | Empleadores y clientes que nunca deben aparecer, separados por comas |

Reservadas para F2/F3: `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_REPO`, `IG_TOKEN`, `IG_USER_ID`, `R2_*`.
Los tokens viven solo en `Settings` (`src/prelo/config.py`); nunca se escriben en logs ni en el repo.
