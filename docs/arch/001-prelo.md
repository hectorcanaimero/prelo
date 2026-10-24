---
type: arch
project_id: prelo
version: 0.3
depends_on:
  - docs/prd/001-prelo.md
generated_by: orch-arch
generated_at: 2026-10-23
title: Prelo — architecture
---

# Prelo — architecture

## Context

El repo solo tiene documentación: el código de la v0 (grafo con `interrupt`, revisión de marca y CI) se borró el
2026-10-23 y se rehace desde cero. El commit `73e0a22` queda como referencia. Esta versión sustituye a la
arquitectura 001 v0.1: conserva sus decisiones D1–D7, cambia cómo se cargan los empleadores bloqueados (D11) y añade
lo que el PRD v0.2 pide para la agenda, Slack, el blog, Instagram, las métricas y el deploy.

Stack impuesto (NFR-7): Python 3.12 con `uv`, LangGraph, Langfuse, Postgres y AWS con Terraform.

```
 Slack (Socket Mode) ◄──────────────┐
        │                            │
        ▼                            │
 slack ──► grafo (LangGraph, checkpointer Postgres) ──► agenda (worker) ──► publicadores
 api ───►   │                                                                ├─ github: PR en site-guria
 (webhook   ├─ agentes: investigador · redator · tradutor · adaptadores      ├─ linkedin
  GitHub)   ├─ marca (determinista)                                          └─ instagram (+ carrossel, R2)
            └─ custos ──► Postgres + Langfuse
 metricas (worker diario) ──► Postgres          GitHub Actions ── tests + evals + deploy
```

## Components

### config — `src/prelo/config.py`
Lee todas las variables de entorno una vez (pydantic-settings). Es el único lugar donde viven los tokens (NFR-3): el
resto recibe clientes ya construidos, nunca el token.

### db — `src/prelo/db/`
Conexión a Postgres, migraciones SQL numeradas (`src/prelo/db/migracoes/NNN_*.sql`) y repositorios por tabla. Es dueño
de las tablas de *Data model*. El checkpointer de LangGraph (`PostgresSaver`) usa la misma base, con sus propias
tablas.

### grafo — `src/prelo/grafo.py`, `src/prelo/estado.py`
El `StateGraph` y el `EstadoPost`. No importa ningún cliente externo: recibe todo por `Dependencias` (ver
*Interfaces*). Es dueño del flujo: qué nodo sigue a cuál, los reintentos de la revisión y los `interrupt()` de
aprobación. `thread_id` = `post_id`, así un post puede esperar días (FR-8).

```
START → investigar → redigir → revisar ─┬─ ok ──────────► traduzir* → pr_blog* ⏸ merge → esperar_deploy*
              ▲                         └─ violação (≤2) ─┐                                     │
              └───────────────────────────────────────────┘                                     ▼
          derivados: adaptar_linkedin / adaptar_carrossel** → revisar → aprovar ⏸ Slack → agendar → END
```
`*` desde F2 · `**` desde F3 · `⏸` = `interrupt()`. En F1 no hay blog: tras `revisar` se va directo a los derivados.

Tras 2 reescrituras fallidas, la pieza llega a `aprovar` con `violacoes` no vacías y Slack no ofrece "Aprobar" (FR-6).
"Editar" vuelve a `redigir` (o al adaptador del canal) con el comentario; "Descartar" va a `END`.

### agentes — `src/prelo/agentes/`
Una función por agente; cada una arma su prompt y llama al `Modelo` inyectado:
- `investigador`: busca con el `Buscador` y devuelve `Fonte`s. No tiene herramientas con efectos (NFR-4).
- `redator`: escribe la pieza madre en español con las fuentes y, si existe, el feedback de violaciones o del editor.
- `tradutor` (F2): pt-BR y en a partir del español.
- `adaptador_linkedin`: post en pt-BR; incluye el link al blog cuando existe.
- `adaptador_carrossel` (F3): textos de las láminas y el prompt de la imagen de fondo.

El contenido de las fuentes entra al prompt dentro de `<fonte>…</fonte>` con la instrucción de tratarlo como datos
(NFR-4).

### modelo — `src/prelo/modelo.py`, `src/prelo/custos.py`
Envuelve el SDK del LLM. Cada llamada registra tokens y USD en la tabla `custos` y la traza en Langfuse, etiquetada
con `post_id` y `agente` (FR-16). Elige el modelo por agente según D4.

### marca — `src/prelo/marca.py`, `marca.toml`
Revisión determinista (D3). Reglas públicas en `marca.toml` (frases de "cara de IA", patrones de cifras y fechas).
Empleadores y clientes desde la variable `PRELO_BLOQUEIA`, nunca desde el repo (NFR-5, D11). Una cifra o fecha cuenta
como con fuente si aparece en algún `trecho` de las `fontes` del post (FR-4).

### slack — `src/prelo/slack.py`
App de Slack Bolt en Socket Mode (D8). Recibe `/prelo <tema>` (FR-1) y `/prelo sugerir` (FR-2, F4). Muestra cada pieza
pendiente con el texto, las fuentes, las violaciones y el costo, y los botones de FR-9. Al pulsar un botón reanuda el
grafo con `Command(resume=…)`.

### agenda — `src/prelo/agenda.py`
Worker que cada minuto toma las piezas `aprovada` y les asigna el siguiente hueco libre de su canal (martes a jueves,
máx. 1 por día, FR-13); cuando llega la hora, llama al publicador, registra la `Publicacao` (FR-14) y avisa en Slack.
Antes de publicar vuelve a comprobar que la pieza tiene `decisao = aprovado` (FR-7, defensa en profundidad).

### publicadores — `src/prelo/publicadores/`
Uno por canal, con la interfaz `Publicador`: `linkedin` (F1), `github` (F2: rama, tres MDX y PR en `site-guria`),
`instagram` (F3). Ninguno decide nada: publican lo que la agenda les pasa.

### api — `src/prelo/api.py`
FastAPI: `GET /saude`, `POST /posts` (D15) y `POST /webhooks/github` (F2). El webhook verifica la firma y, si un PR `prelo/<post_id>` se
mergeó, reanuda el grafo de ese post.

### deploy_blog — `src/prelo/deploy_blog.py` (F2)
Espera a que la URL pública del post responda 200 (D10) y entonces reanuda el grafo para generar los derivados.

### mdx — `src/prelo/mdx.py` (F2)
Convierte la pieza madre en los tres MDX con el frontmatter que exige la colección `blog` de `site-guria` (NFR-8).

### carrossel — `src/prelo/carrossel.py`, `templates/carrossel/` (F3)
Rellena plantillas HTML con los textos de las láminas y las pasa a PNG con Playwright (D5). La imagen de fondo la
genera `imagens.py` con un prompt que prohíbe texto (FR-12); los PNG se suben a R2 para que Instagram los lea por URL.

### metricas — `src/prelo/metricas.py` (F4)
Worker diario que lee reacciones y comentarios de cada `Publicacao` de LinkedIn e Instagram y los guarda (FR-15).

### sugestoes — `src/prelo/sugestoes.py` (F4)
Junta commits recientes de los repos de Héctor (GitHub API), la ruta de estudio y noticias de IA, y pide al `Modelo`
3 temas con su origen (FR-2).

### juizo — `src/prelo/juizo.py` (F5)
Cliente de Jev (TypeSafe System One, `typesafe-sdk`, `TYPESAFE_API_KEY`) detrás de un protocolo `Juiz` con
`avaliar(estado: dict, perguntas: dict) -> Respostas`. Devuelve juicios tipados (Noul, Choice, Score) con
probabilidades, no texto. Lo usan cuatro puntos, todos con la política en código y nunca para aprobar (FR-7):
- `porta_aprovacao` (FR-17): Score "probabilidad de aprobación sin edición" + Nouls por dimensión (gancho, claridad,
  voz de Héctor, cara de IA). Bajo el umbral y con `tentativas < 2`, vuelve a `redigir` con las dimensiones fallidas
  como feedback.
- `verificacao` (FR-18): un Noul por par (afirmación, `trecho`) — "¿el fragmento sostiene la afirmación?". Las
  afirmaciones las segmenta el código; las sin apoyo van a Slack como aviso. También sustituye al LLM juez de
  fidelidad en `evals/` (NFR-1, NFR-2).
- `fontes` (NFR-4): un Noul por fuente — "¿contiene instrucciones dirigidas a un asistente de IA?". Una fuente
  marcada se descarta antes de llegar al redator.
- `sugestoes` (FR-2): Scores por candidato (interés para la audiencia, novedad frente a lo publicado, encaje con los
  temas de Héctor) combinados con pesos en código para elegir los 3 temas.

### video — `src/prelo/video.py`, `templates/video/` (F5)
Reel vertical 1080×1920 con HyperFrames: una composición HTML (`templates/video/reel.html`) con huecos de texto,
timing en atributos `data-*`, renderizada a MP4 con `npx hyperframes render`. Reutiliza los textos de las láminas del
carrusel y la imagen de fondo de `imagens.py`; el MP4 se sube a R2 y `publicadores/instagram` lo publica como
`REELS`. Canal nuevo en `pecas`: `reel`.

### evals — `evals/`
Casos fijos y métricas: fidelidad a las fuentes, estilo, calidad de traducción y violaciones de marca. Corren en CI y
fallan si una métrica baja de su umbral (NFR-2).

### infra — `docker-compose.yml`, `infra/terraform/`
Compose con `prelo` (api + slack + workers), Postgres y Langfuse (NFR-6). En F4, Terraform crea una EC2 que corre el
mismo compose (D12).

## Data model

Postgres. Migraciones en `src/prelo/db/migracoes/`, empezando por `001_inicial.sql`.

| Tabla | Campos clave | Dueño |
| --- | --- | --- |
| `posts` | `id` (uuid, = `thread_id`), `tema`, `origem` (`editor` \| `sugestao`), `criado_em`, `estado` | grafo |
| `fontes` | `post_id`, `url`, `titulo`, `trecho` | grafo |
| `pecas` | `id`, `post_id`, `canal` (`blog` \| `linkedin` \| `instagram`), `conteudo` (jsonb, por idioma), `violacoes` (jsonb), `status` (`pendente` \| `aprovada` \| `agendada` \| `publicada` \| `descartada`), `decisao`, `comentario`, `agendada_para` | grafo; agenda cambia `status` y `agendada_para` |
| `publicacoes` | `id`, `peca_id`, `canal`, `url`, `publicada_em`, `id_externo` | agenda |
| `metricas` | `publicacao_id`, `coletada_em`, `reacoes`, `comentarios` (jsonb) | metricas |
| `custos` | `post_id`, `agente`, `modelo`, `tokens_entrada`, `tokens_saida`, `usd`, `criado_em` | modelo |

El `EstadoPost` del grafo es el estado de trabajo; las tablas son el registro que leen Slack, la agenda y las métricas.
El grafo escribe en `posts`, `fontes` y `pecas` al pasar por cada nodo.

## Interfaces

Todas en `src/prelo/interfaces.py` (dueño: F1.1), salvo `EstadoPost`.

```python
class Fonte(TypedDict):
    url: str; titulo: str; trecho: str

class Violacao(TypedDict):
    regra: Literal["empregador", "cifra_sem_fonte", "frase_ia"]; trecho: str; detalhe: str

class Texto(TypedDict):          # un idioma de una pieza
    titulo: str; resumo: str; corpo: str

class EstadoPost(TypedDict):     # src/prelo/estado.py
    post_id: str
    tema: str
    fontes: list[Fonte]
    rascunho: dict[str, Texto]                 # "es" | "pt" | "en"
    derivados: dict[str, dict]                 # canal -> contenido del canal
    violacoes: list[Violacao]
    tentativas: int
    decisao: Literal["aprovado", "editar", "descartar"] | None
    comentario: str | None
    url_blog: str | None

class Modelo(Protocol):
    def gerar(self, prompt: str, *, agente: str, post_id: str) -> str: ...

class Buscador(Protocol):
    def buscar(self, consulta: str, *, max_resultados: int = 5) -> list[Fonte]: ...

class Publicador(Protocol):
    canal: str
    def publicar(self, peca: Peca) -> Publicacao: ...   # Peca/Publicacao: dataclasses de las tablas

def revisar(texto: str, fontes: list[Fonte], regras: Regras) -> list[Violacao]: ...   # marca.py

@dataclass
class Dependencias:              # lo que recibe grafo.construir(deps, checkpointer)
    # El grafo no importa agentes, marca ni slack: los recibe ya armados (app.py), y los tests pasan dobles.
    investigar: Callable[..., list[Fonte]]           # (tema, *, post_id)
    redigir: Callable[..., Texto]                    # (tema, fontes, feedback: str | None, *, post_id)
    adaptar: dict[str, Callable[..., dict]]          # canal -> (texto, url_blog: str | None, feedback, *, post_id)
    revisar: Callable[[str, list[Fonte]], list[Violacao]]
    notificar: Callable[[Peca], None]                # avisa en Slack que una pieza espera aprobación
    repo: Repositorio                                # db
```

`Modelo` y `Buscador` los usan los agentes por dentro; el grafo no los ve. F2 añade a `Dependencias` `traduzir` y
`abrir_pr`; F3, el adaptador `instagram`.

- **Iniciar y reanudar un post** (`grafo.py`): `iniciar(grafo, tema, origem) -> post_id` y
  `retomar(grafo, post_id, decisao, comentario=None)`. Por dentro, `retomar` hace
  `grafo.invoke(Command(resume={"decisao": d, "comentario": c}), config={"configurable": {"thread_id": post_id}})`.
  Slack, el webhook y `deploy_blog` solo usan estas dos funciones.
- **Slack**: `action_id` ∈ `prelo_aprovar` | `prelo_editar` | `prelo_descartar`; `value` = `{"post_id": …,
  "peca_id": …}` en JSON. "Editar" abre un modal con un campo `comentario`.
- **API para Hermes** (D15): `POST /posts` con `{"tema": str}` y cabecera `Authorization: Bearer <PRELO_API_TOKEN>`
  → `202 {"post_id": …}`; llama a `iniciar(grafo, tema, "editor")`. Sin token válido, 401. No hay endpoint para
  aprobar: la aprobación solo entra por los botones de Slack.
- **App de Slack**: `slack-manifest.yml` en la raíz (Socket Mode, comando `/prelo`, interactividad, scopes
  `chat:write`, `commands`); se crea una vez en api.slack.com/apps a partir del manifest.
- **GitHub (F2)**: rama `prelo/<post_id>`; el webhook escucha `pull_request` con `action = closed` y `merged = true`.
- **MDX (F2)**: un archivo por idioma en `site-guria`; las rutas y el frontmatter exactos se copian del schema de la
  colección `blog` en F2.1 y se fijan en `mdx.py` con un test de contrato.
- **Plantillas de carrusel (F3)**: `templates/carrossel/<nome>.html` con los huecos `{{titulo}}`, `{{texto}}`,
  `{{imagem_url}}`, `{{n}}/{{total}}`; salida PNG 1080×1350.
- **Variables de entorno**: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `SLACK_BOT_TOKEN`,
  `SLACK_APP_TOKEN`, `SLACK_CANAL`, `LINKEDIN_TOKEN`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `IG_TOKEN`,
  `IG_USER_ID`, `R2_*`, `LANGFUSE_*`, `PRELO_API_TOKEN`, `TYPESAFE_API_KEY`, `PRELO_BLOQUEIA` (lista separada por comas). Todas en `.env.example` sin valores.

## Decisions

- **D1 — Motor del flujo.** Chosen: LangGraph. Rejected: Agno, porque no trae `interrupt` + checkpointer y la
  aprobación puede tardar días.
- **D2 — CMS del blog.** Chosen: Git (PR en `site-guria`). Rejected: un CMS headless, porque el sitio es Astro
  estático y el PR ya da revisión, historial y validación del schema en CI.
- **D3 — Revisión de marca.** Chosen: código determinista. Rejected: un LLM revisor, porque puede saltarse la regla y
  una regex no.
- **D4 — Modelos.** Chosen: modelo fuerte para `redator`, barato para `tradutor` y adaptadores. Rejected: un solo
  modelo, porque no cabe en NFR-1 sin bajar la calidad de la pieza madre.
- **D5 — Texto de los carruseles.** Chosen: plantillas HTML → PNG con Playwright. Rejected: texto dentro de la imagen
  generada, porque sale deformado.
- **D6 — Observabilidad.** Chosen: Langfuse self-hosted. Rejected: LangSmith, porque es de pago y no muestra
  operación de infraestructura propia (G5).
- **D7 — Servidor.** Chosen: FastAPI propio, el grafo como librería. Rejected: LangGraph Agent Server, por la
  dependencia de licencia.
- **D8 — Slack.** Chosen: Socket Mode. Rejected: Events API por HTTP, porque exige una URL pública también en local.
- **D15 — Hermes y Slack.** Chosen: Prelo tiene su propia app de Slack (D8) para pedir y decidir aprobaciones con
  botones, y Hermes (que ya vive en el mismo Slack) solo puede iniciar posts por `POST /posts`. El cron de LinkedIn de
  Hermes se apaga cuando M1 publica. Rejected: aprobar conversando con Hermes, porque un LLM interpretaría la
  aprobación y FR-7 exige una decisión explícita; y compartir la app de Hermes, porque dos conexiones Socket Mode de
  la misma app se reparten los eventos.
- **D16 — Juicios rápidos.** Chosen: Jev (TypeSafe System One) para juicios tipados con probabilidad (FR-17, FR-18,
  fuentes y sugerencias). Rejected: pedir esos juicios al LLM generativo, porque cuesta más por llamada, devuelve
  texto que hay que parsear y no da probabilidades calibradas para fijar umbrales. La revisión de marca sigue siendo
  determinista (D3): Jev solo aporta señales blandas y nunca aprueba.
- **D17 — Video.** Chosen: HyperFrames (HTML → MP4), que extiende el enfoque de plantillas HTML de D5. Rejected:
  video generado por IA (Veo, Sora), porque el texto sale deformado (mismo motivo que D5) y el costo por pieza no cabe
  en NFR-1.
- **D9 — Agenda.** Chosen: tabla `pecas` + worker. Rejected: dormir dentro del grafo hasta la fecha, porque cambiar
  la franja obligaría a tocar hilos ya pausados.
- **D10 — Saber que el blog está publicado.** Chosen: consultar la URL pública hasta que responda 200. Rejected:
  depender del workflow de deploy de `site-guria`, que aún no se conoce (pregunta abierta del PRD).
- **D11 — Lista de empleadores.** Chosen: variable de entorno `PRELO_BLOQUEIA`. Rejected: `marca.local.toml` fuera de
  git (v0.1), porque en la nube igual hace falta un secreto y así hay un solo camino.
- **D12 — Nube.** Chosen: una EC2 con el mismo `docker compose`, creada con Terraform. Rejected: ECS + RDS, porque
  multiplica el costo para un solo usuario y se aleja del entorno local (NFR-6).
- **D13 — Búsqueda.** Chosen: Tavily detrás de `Buscador`. Rejected: scraping propio, por mantenimiento; la interfaz
  permite cambiarlo.
- **D14 — Imagen de fondo del carrusel.** Chosen: API de imágenes de OpenAI (`gpt-image-1`) detrás de una función
  `gerar_imagem(prompt) -> bytes`. Rejected: Midjourney, porque no tiene API oficial.

## Risks

- El token de LinkedIn caduca a los 60 días, *mitigation:* la agenda avisa en Slack 7 días antes y un fallo de
  publicación deja la pieza en `aprovada`, no la pierde.
- La API de Instagram exige una cuenta Business o Creator vinculada a una página de Facebook (pregunta abierta),
  *mitigation:* F3 empieza por un esqueleto con publicador falso; el real se hace cuando esté la cuenta.
- Langfuse v3 self-hosted pide ClickHouse y Redis y puede no caber en una EC2 pequeña, *mitigation:* medirlo en F4.4;
  si no cabe, Langfuse Cloud (plan gratis) detrás de las mismas variables.
- El costo por post supera USD 0,50, *mitigation:* `custos` lo mide desde F1 y las evals marcan la regresión antes de
  F2, cuando se triplica el texto.
- `site-guria` cambia el schema de `blog`, *mitigation:* el CI del sitio rechaza el PR y el test de contrato de
  `mdx.py` se actualiza a partir del schema.
- Una fuente con instrucciones escondidas, *mitigation:* el investigador no tiene herramientas con efectos, las
  fuentes van delimitadas y la revisión de marca y la aprobación humana van después.

## Requirement coverage

| Requirement | Component(s) |
| --- | --- |
| FR-1 | slack, api (Hermes), grafo |
| FR-2 | sugestoes, slack |
| FR-3 | agentes (investigador), db (`fontes`), slack |
| FR-4 | marca |
| FR-5 | agentes (redator, tradutor) |
| FR-6 | marca, grafo, slack |
| FR-7 | grafo (`interrupt`), agenda |
| FR-8 | grafo (checkpointer Postgres) |
| FR-9 | slack, grafo |
| FR-10 | mdx, publicadores/github, api, deploy_blog |
| FR-11 | agentes (adaptador_linkedin), publicadores/linkedin |
| FR-12 | agentes (adaptador_carrossel), carrossel, publicadores/instagram |
| FR-13 | agenda |
| FR-14 | agenda, db (`publicacoes`) |
| FR-15 | metricas |
| FR-16 | modelo, db (`custos`), slack |
| FR-17 | juizo (porta_aprovacao), grafo, slack |
| FR-18 | juizo (verificacao), slack, evals |
| FR-19 | video, publicadores/instagram, agenda |
| NFR-1 | modelo (D4), custos, evals |
| NFR-2 | evals, CI |
| NFR-3 | config, modelo (trazas sin secretos) |
| NFR-4 | agentes (delimitadores, sin herramientas con efectos) |
| NFR-5 | marca (`PRELO_BLOQUEIA`) |
| NFR-6 | infra (compose) |
| NFR-7 | grafo, modelo, infra (Terraform) |
| NFR-8 | mdx |

## Work breakdown

Cada fase es un hito del PRD y empieza por un esqueleto andante: el flujo completo de punta a punta con dobles en vez
de servicios externos. Después, los paquetes de la fase corren en paralelo sobre archivos disjuntos y el último los
conecta. `F0` lo usa la tarea de ejemplo de `orch init`; el trabajo empieza en `F1`.

### F1 — LinkedIn de punta a punta con aprobación en Slack (M1)
- **F1.1 — esqueleto**: proyecto `uv`, compose (Postgres + Langfuse), `config`, migración inicial, `interfaces.py`,
  `estado.py` y `grafo.py` con nodos que usan dobles; test que recorre tema → aprobación → publicación falsa y
  sobrevive a un reinicio. Files/dirs: `pyproject.toml`, `uv.lock`, `docker-compose.yml`, `Dockerfile`,
  `.env.example`, `src/prelo/__init__.py`, `src/prelo/config.py`, `src/prelo/interfaces.py`, `src/prelo/estado.py`,
  `src/prelo/grafo.py`, `src/prelo/db/`, `tests/conftest.py`, `tests/test_grafo.py`, `.github/workflows/ci.yml`.
- **F1.2 — marca**: `revisar` y sus reglas. Files/dirs: `src/prelo/marca.py`, `marca.toml`, `tests/test_marca.py`.
  Depends on: F1.1.
- **F1.3 — agentes y costo**: `investigador`, `redator`, `adaptador_linkedin`, `Modelo` real, `Buscador` Tavily y
  registro de `custos`. Files/dirs: `src/prelo/agentes/`, `src/prelo/modelo.py`, `src/prelo/custos.py`,
  `src/prelo/buscador.py`, `tests/test_agentes.py`, `tests/test_custos.py`. Depends on: F1.1.
- **F1.4 — slack**: comando `/prelo`, mensajes de pieza pendiente y botones. Files/dirs: `src/prelo/slack.py`,
  `tests/test_slack.py`. Depends on: F1.1.
- **F1.5 — agenda y LinkedIn**: worker de agenda y `publicadores/linkedin`. Files/dirs: `src/prelo/agenda.py`,
  `src/prelo/publicadores/__init__.py`, `src/prelo/publicadores/linkedin.py`, `tests/test_agenda.py`,
  `tests/test_linkedin.py`. Depends on: F1.1.
- **F1.6 — evals**: casos y métricas de estilo, fidelidad y marca en CI. Files/dirs: `evals/`,
  `.github/workflows/evals.yml`. Depends on: F1.2, F1.3.
- **F1.7 — conexión**: `app.py` arma las `Dependencias` reales y arranca api, slack y agenda en un proceso; README.
  Files/dirs: `src/prelo/app.py`, `src/prelo/api.py`, `README.md`. Depends on: F1.2, F1.3, F1.4, F1.5.

### F2 — El blog como pieza madre (M2)
- **F2.1 — esqueleto del blog**: nodos `traduzir`, `pr_blog` (interrupt) y `esperar_deploy` con dobles; LinkedIn pasa
  a generarse tras el deploy con `url_blog`. Fija las rutas y el frontmatter MDX a partir del schema de `site-guria`.
  Files/dirs: `src/prelo/grafo.py`, `src/prelo/estado.py`, `src/prelo/interfaces.py`, `tests/test_grafo_blog.py`.
- **F2.2 — traducción y MDX**: `tradutor` y `mdx.py` con test de contrato. Files/dirs: `src/prelo/agentes/tradutor.py`,
  `src/prelo/mdx.py`, `tests/test_mdx.py`, `tests/test_tradutor.py`. Depends on: F2.1.
- **F2.3 — GitHub**: `publicadores/github` (rama + PR) y el webhook. Files/dirs: `src/prelo/publicadores/github.py`,
  `src/prelo/webhooks.py`, `tests/test_github.py`. Depends on: F2.1.
- **F2.4 — deploy del blog**: espera de la URL pública. Files/dirs: `src/prelo/deploy_blog.py`,
  `tests/test_deploy_blog.py`. Depends on: F2.1.
- **F2.5 — conexión y evals de traducción**: Files/dirs: `src/prelo/app.py`, `src/prelo/api.py`,
  `evals/traducao/`. Depends on: F2.2, F2.3, F2.4.

### F3 — Carrusel de Instagram (M3)
- **F3.1 — esqueleto del carrusel**: nodo `adaptar_carrossel` y canal `instagram` en la agenda con dobles.
  Files/dirs: `src/prelo/grafo.py`, `src/prelo/estado.py`, `tests/test_grafo_carrossel.py`.
- **F3.2 — render**: plantillas y PNG con Playwright. Files/dirs: `templates/carrossel/`, `src/prelo/carrossel.py`,
  `tests/test_carrossel.py`. Depends on: F3.1.
- **F3.3 — imágenes y R2**: imagen de fondo sin texto y subida. Files/dirs: `src/prelo/imagens.py`,
  `src/prelo/r2.py`, `src/prelo/agentes/adaptador_carrossel.py`, `tests/test_imagens.py`. Depends on: F3.1.
- **F3.4 — Instagram**: `publicadores/instagram`. Files/dirs: `src/prelo/publicadores/instagram.py`,
  `tests/test_instagram.py`. Depends on: F3.1.
- **F3.5 — conexión**: Files/dirs: `src/prelo/app.py`, `Dockerfile`. Depends on: F3.2, F3.3, F3.4.

### F4 — Métricas, sugerencias y Prelo en la nube (M4)
- **F4.1 — esqueleto**: tabla `metricas`, worker diario y `/prelo sugerir` con dobles. Files/dirs:
  `src/prelo/db/migracoes/`, `src/prelo/slack.py`, `tests/test_metricas_fluxo.py`.
- **F4.2 — métricas**: lectura de reacciones y comentarios de LinkedIn e Instagram. Files/dirs:
  `src/prelo/metricas.py`, `tests/test_metricas.py`. Depends on: F4.1.
- **F4.3 — sugerencias**: Files/dirs: `src/prelo/sugestoes.py`, `tests/test_sugestoes.py`. Depends on: F4.1.
- **F4.4 — Terraform**: EC2, red, secretos y backups de Postgres. Files/dirs: `infra/terraform/`. Depends on: F4.1.
- **F4.5 — deploy continuo y conexión**: Files/dirs: `.github/workflows/deploy.yml`, `src/prelo/app.py`. Depends on:
  F4.2, F4.3, F4.4.

### F5 — Decisiones con Jev y Reels (M5)
- **F5.1 — juizo**: cliente Jev y protocolo `Juiz`. Files/dirs: `src/prelo/juizo.py`, `tests/test_juizo.py`.
- **F5.2 — porta de aprobación y fuentes**: nodo en el grafo y filtro de fuentes. Depends on: F5.1.
- **F5.3 — verificación de afirmaciones y evals**. Depends on: F5.1.
- **F5.4 — ranking de sugerencias**. Depends on: F5.1.
- **F5.5 — Reel con HyperFrames**: plantilla, render y publicación. Independiente de F5.1.
- **F5.6 — conexión**. Depends on: F5.2, F5.3, F5.4, F5.5.

