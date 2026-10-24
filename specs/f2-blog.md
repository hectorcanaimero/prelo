---
type: spec
project_id: prelo
phase: 2
version: 0.1
depends_on:
  - docs/prd/001-prelo.md
  - docs/arch/001-prelo.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-24
title: El blog como pieza madre
---

# F2 — El blog como pieza madre

Hito M2 del PRD (FR-5, FR-10, FR-11). La pieza madre se traduce a pt-BR y en, se entrega como PR en `site-guria`
con tres MDX, el merge es la aprobación, y tras el deploy el post de LinkedIn se genera con el link al blog. Parte de
F1 terminada.

## F2.1 — Package: esqueleto del blog

### F2.1.T1 — Nodos traduzir, pr_blog y esperar_deploy con dobles

Extiende el grafo según *grafo* de docs/arch/001-prelo.md: tras `revisar` ok van `traduzir → pr_blog` (abre el PR y
hace `interrupt()` hasta el merge) `→ esperar_deploy` (otro `interrupt()` hasta que `deploy_blog` reanude con la URL
pública) y solo entonces los derivados, con `url_blog` en el estado. Añade a `Dependencias` `traduzir(texto, *,
post_id) -> dict[str, Texto]` y `abrir_pr(post_id, textos) -> str` (URL del PR), como fija *Interfaces*. Crea la
pieza de canal `blog` en `pecas`; el merge del PR registra `decisao = aprovado` para esa pieza (FR-7). Si el PR se
cierra sin merge, el post termina sin derivados. Mantén verdes los tests de F1 adaptando sus dobles.

Done when: these tests pass in `tests/test_grafo_blog.py`, con dobles — un tema sin violaciones llama a `traduzir`
y a `abrir_pr` y queda pausado en `pr_blog`; reanudar con merge pausa en `esperar_deploy`; reanudar con la URL
llama al adaptador de LinkedIn con esa `url_blog`; la pieza `blog` queda con `decisao = aprovado` tras el merge;
un PR cerrado sin merge termina el post sin llamar al adaptador; y `tests/test_grafo.py` sigue pasando.

- **Model**: claude/claude-opus-5-5
- **Estimate**: 4h
- **Reason**: Cambia el flujo central con dos interrupts nuevos; diseño crítico.
- **Dependencies**: F1.7.T1
- **Files**:
  - `src/prelo/grafo.py`
  - `src/prelo/estado.py`
  - `src/prelo/interfaces.py`
  - `tests/test_grafo.py`
  - `tests/test_grafo_blog.py`

## F2.2 — Package: traducción y MDX

### F2.2.T1 — Agente tradutor

Implementa `src/prelo/agentes/tradutor.py` con la firma de `Dependencias.traduzir`: a partir del `Texto` en español
produce `pt` y `en` con título, resumen y cuerpo, usando el modelo barato (D4) vía `Modelo`. Mantiene intactos los
bloques de código, los links y las cifras del original (las cifras ya fueron validadas por la marca).

Done when: these tests pass in `tests/test_tradutor.py`, con un `Modelo` falso — devuelve las claves `es`, `pt` y
`en` y cada una tiene los tres campos; un bloque de código del original aparece idéntico en las traducciones; si el
modelo devuelve una traducción sin cuerpo, levanta un error legible; el agente usado al llamar al modelo es
`tradutor`.

- **Model**: agy/gemini-4-argon-medium
- **Estimate**: 2h
- **Reason**: Prompt y parseo; la calidad la miden las evals de F2.5.
- **Dependencies**: F2.1.T1
- **Files**:
  - `src/prelo/agentes/tradutor.py`
  - `tests/test_tradutor.py`

### F2.2.T2 — mdx.py con test de contrato contra site-guria

Lee el schema de la colección `blog` de `site-guria` (`src/content/config.ts` o equivalente, en
github.com/hectorcanaimero/site-guria; usa `gh` con `GITHUB_TOKEN`) y fija en `src/prelo/mdx.py` las rutas por
idioma y el frontmatter exacto (NFR-8). `gerar_mdx(post_id, textos, data) -> dict[str, str]` devuelve ruta →
contenido para los tres idiomas. Guarda una copia del schema leído en `tests/fixtures/site_guria_blog_schema.ts` y
escribe un test de contrato que compara los campos del frontmatter con ese schema, para que un cambio del sitio
rompa el test (riesgo del ARCH).

Done when: these tests pass in `tests/test_mdx.py` — se generan tres archivos, uno por idioma, en las rutas fijadas;
cada frontmatter tiene todos los campos obligatorios del schema y ninguno desconocido; un título con comillas y dos
puntos produce YAML válido; el slug es el mismo en los tres idiomas; el cuerpo sale tal cual.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 3h
- **Reason**: Hay que leer un repo externo y fijar un contrato; requiere criterio.
- **Dependencies**: F2.1.T1
- **Files**:
  - `src/prelo/mdx.py`
  - `tests/fixtures/site_guria_blog_schema.ts`
  - `tests/test_mdx.py`

## F2.3 — Package: GitHub

### F2.3.T1 — Publicador de GitHub: rama y PR

Implementa `src/prelo/publicadores/github.py` con la API de GitHub vía `httpx` y la función `abrir_pr(post_id,
textos)` de `Dependencias`: crea la rama `prelo/<post_id>` en `site-guria`, sube los tres MDX de `mdx.gerar_mdx` en
un commit y abre el PR con el título del post y el link a las fuentes en la descripción. Devuelve la URL del PR. Si la
rama ya existe, actualiza el PR en vez de duplicarlo. Ningún error ni log contiene `GITHUB_TOKEN`.

Done when: these tests pass in `tests/test_github.py`, con `respx` — se crea la rama `prelo/<post_id>` desde la rama
por defecto; el commit contiene los tres archivos con su contenido; el PR se abre contra la rama por defecto y la
función devuelve su URL; con la rama ya existente no se abre un segundo PR; un 403 levanta un error sin el token.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 3h
- **Reason**: Cliente de la API de Git data con varios pasos.
- **Dependencies**: F2.2.T2
- **Files**:
  - `src/prelo/publicadores/github.py`
  - `tests/test_github.py`

### F2.3.T2 — Webhook de GitHub

Implementa `src/prelo/webhooks.py`: un `APIRouter` de FastAPI con `POST /webhooks/github` que verifica la firma
`X-Hub-Signature-256` con `GITHUB_WEBHOOK_SECRET` (comparación en tiempo constante) y, para eventos `pull_request`
con `action = closed`, rama `prelo/<post_id>` y `merged = true`, llama a `retomar(post_id, "aprovado")`; con
`merged = false`, a `retomar(post_id, "descartar")` (ver *Interfaces → GitHub*). Otros eventos responden 204 sin
efecto. Recibe `retomar` inyectado; `api.py` lo monta en F2.5.

Done when: these tests pass in `tests/test_webhooks.py` — una firma inválida responde 401 y no llama a `retomar`; un
PR mergeado de `prelo/abc` llama a `retomar("abc", "aprovado")`; un PR cerrado sin merge llama a
`retomar("abc", "descartar")`; un PR de otra rama o un evento `push` responde 204 sin efecto; reenviar el mismo
evento no reanuda dos veces.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 2h
- **Reason**: Verificación de firma: sensible pero acotada y bien conocida.
- **Dependencies**: F2.1.T1
- **Files**:
  - `src/prelo/webhooks.py`
  - `tests/test_webhooks.py`

## F2.4 — Package: deploy del blog

### F2.4.T1 — Espera del deploy del blog

Implementa `src/prelo/deploy_blog.py` según D10: para cada post pausado en `esperar_deploy`, consulta la URL pública
esperada en guria.lat/blog (la que da `mdx.py` para `es`) hasta que responda 200, con espera creciente y un límite
configurable; entonces llama a `retomar` con la URL. Si se agota el límite, avisa en Slack y deja el post pausado.
Recibe cliente HTTP, `retomar`, aviso y reloj inyectados.

Done when: these tests pass in `tests/test_deploy_blog.py`, con `respx` y reloj falso — un 404 y luego un 200
reanudan una sola vez con la URL; tres 404 seguidos esperan intervalos crecientes; agotar el límite genera un aviso y
no reanuda.

- **Model**: agy/gemini-3.8-flash-medium
- **Estimate**: 2h
- **Reason**: Bucle de sondeo simple.
- **Dependencies**: F2.1.T1
- **Files**:
  - `src/prelo/deploy_blog.py`
  - `tests/test_deploy_blog.py`

## F2.5 — Package: conexión y evals

### F2.5.T1 — Conexión del blog en app.py y api.py

Añade a `montar_dependencias` el `tradutor` y `abrir_pr`, monta el router de `webhooks.py` en `api.py` y arranca el
sondeo de `deploy_blog` junto a la agenda. Actualiza `README.md` con cómo configurar el webhook en `site-guria`.

Done when: these tests pass in `tests/test_app.py` — `montar_dependencias` incluye `traduzir` y `abrir_pr`;
`POST /webhooks/github` está montado y responde 401 a una firma inválida; con dobles, un tema llega a una pieza de
LinkedIn pendiente con `url_blog` tras simular merge y deploy.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 2h
- **Reason**: Cableado.
- **Dependencies**: F2.2.T1, F2.3.T1, F2.3.T2, F2.4.T1
- **Files**:
  - `src/prelo/app.py`
  - `src/prelo/api.py`
  - `tests/test_app.py`
  - `README.md`

### F2.5.T2 — Evals de traducción

Añade `evals/traducao/` al runner de F1.6: al menos 5 casos (texto en español con código, cifras y links) y la
métrica de calidad de traducción (LLM juez barato con rúbrica: fidelidad, naturalidad, cifras y links intactos) con
su umbral (NFR-2). No toques el runner: lo descubre solo.

Done when: `uv run python evals/run.py traducao` corre los casos y reporta la métrica; con un tradutor falso que
cambia una cifra, la corrida falla nombrando el caso.

- **Model**: agy/gemini-4-argon-medium
- **Estimate**: 2h
- **Reason**: Casos y rúbrica; requiere criterio de calidad.
- **Dependencies**: F2.2.T1
- **Files**:
  - `evals/traducao/`
