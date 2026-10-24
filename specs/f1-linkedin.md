---
type: spec
project_id: prelo
phase: 1
version: 0.1
depends_on:
  - docs/prd/001-prelo.md
  - docs/arch/001-prelo.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-24
title: LinkedIn de punta a punta con aprobación en Slack
---

# F1 — LinkedIn de punta a punta con aprobación en Slack

Hito M1 del PRD (FR-1, FR-3, FR-4, FR-6, FR-7, FR-8, FR-9, FR-11, FR-13, FR-14, FR-16). Un tema enviado por Slack
produce un post de LinkedIn en pt-BR, revisado por la marca, aprobado en Slack y publicado en la siguiente franja
libre. En esta fase no hay blog: tras `revisar` el grafo va directo a los derivados (ver *grafo* en
docs/arch/001-prelo.md).

Convenciones para todas las tareas: Python 3.12 con `uv`, código en `src/prelo/`, tests con `pytest` en `tests/`.
Las tareas que dependen solo de F1.1.T4 corren en paralelo con la base de datos: en sus tests usan un `Repositorio`
en memoria escrito en el propio test. La fixture `pg_url` de `tests/conftest.py` (F1.1.T2) la usan solo las tareas
que dependen de F1.1.T2. Ningún test llama a un
servicio externo real: se usan dobles o `respx` para HTTP.

## F1.1 — Package: esqueleto

### F1.1.T1 — Proyecto uv, compose, config y CI

Crea el esqueleto del proyecto según la sección *Components → config* e *infra* de docs/arch/001-prelo.md.

- `pyproject.toml` con `uv` (Python 3.12) y las dependencias de F1: `langgraph`, `langgraph-checkpoint-postgres`,
  `psycopg[binary,pool]`, `anthropic`, `langfuse`, `slack-bolt`, `fastapi`, `uvicorn`, `tavily-python`,
  `pydantic-settings`, `httpx`; de desarrollo `pytest`, `respx`, `ruff`. Genera `uv.lock`.
- `src/prelo/__init__.py`, y paquetes vacíos `src/prelo/agentes/__init__.py` y `src/prelo/publicadores/__init__.py`
  para que las tareas paralelas no se pisen.
- `src/prelo/config.py`: una clase `Settings` (pydantic-settings) con todas las variables de *Interfaces → Variables
  de entorno*; `PRELO_BLOQUEIA` se expone como `list[str]` (separada por comas, sin espacios sobrantes, vacía si no
  existe). Los tokens son `SecretStr` para que nunca salgan en un `repr` ni en un log (NFR-3).
- `.env.example` con todas las variables y sin valores.
- `docker-compose.yml` con `postgres` y Langfuse self-hosted (con sus dependencias) y un servicio `prelo` que usa el
  `Dockerfile`; `docker compose up` debe levantar todo (NFR-6).
- `Dockerfile` multi-stage con `uv`.
- `.github/workflows/ci.yml`: `ruff check`, `pytest` con un servicio Postgres y `TEST_DATABASE_URL` apuntándolo.

Done when: these tests pass in `tests/test_config.py` — `PRELO_BLOQUEIA="Acme, Foo ,"` produce `["Acme", "Foo"]`;
sin `PRELO_BLOQUEIA` la lista es vacía; el `repr` de `Settings` no contiene el valor de `SLACK_BOT_TOKEN`. Además
`uv run ruff check` pasa y `docker compose config` valida el compose.

- **Model**: agy/gemini-4-argon-medium
- **Estimate**: 3h
- **Reason**: Scaffolding con Langfuse v3 en compose tiene piezas no triviales; standard basta.
- **Dependencies**:
- **Files**:
  - `pyproject.toml`
  - `uv.lock`
  - `docker-compose.yml`
  - `Dockerfile`
  - `.env.example`
  - `src/prelo/__init__.py`
  - `src/prelo/agentes/__init__.py`
  - `src/prelo/publicadores/__init__.py`
  - `src/prelo/config.py`
  - `tests/test_config.py`
  - `.github/workflows/ci.yml`

### F1.1.T2 — Base de datos: migración inicial y repositorio

Implementa *db* según *Data model* de docs/arch/001-prelo.md: conexión a Postgres con `psycopg`, un aplicador de
migraciones SQL numeradas (`src/prelo/db/migracoes/NNN_*.sql`, registra las aplicadas en una tabla propia y es
idempotente) y `001_inicial.sql` con las tablas `posts`, `fontes`, `pecas`, `publicacoes` y `custos`. La tabla
`metricas` NO va aquí: llega en F4.1.

Implementa en `src/prelo/db/repositorio.py` el protocolo `Repositorio` de `src/prelo/interfaces.py` (F1.1.T4), con las
dataclasses `Post`, `Peca`, `Publicacao` y `Custo` que define ese archivo, y los métodos que usan los demás componentes: crear y leer posts, guardar fuentes, crear/actualizar piezas
(`status`, `decisao`, `comentario`, `agendada_para`), listar piezas por `status` y canal, registrar publicaciones y
costos, y sumar costos por post y agente. No cambies las firmas de `interfaces.py`: si falta algo, añádelo solo en la
implementación.

`tests/conftest.py` define la fixture `pg_url`: lee `TEST_DATABASE_URL`, salta el test si no existe, crea un schema
limpio por test y aplica las migraciones.

Done when: these tests pass in `tests/test_db.py` — aplicar las migraciones dos veces no falla ni duplica nada; un
post con dos fuentes se lee con sus dos fuentes; cambiar el `status` de una pieza a `aprovada` y listar por ese
`status` la devuelve; la suma de costos de un post agrupa por agente y da el total correcto.

- **Model**: muse/muse-wonder-1.0
- **Estimate**: 3h
- **Reason**: SQL y repositorio sin decisiones de diseño abiertas.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/db/__init__.py`
  - `src/prelo/db/conexao.py`
  - `src/prelo/db/migrar.py`
  - `src/prelo/db/migracoes/001_inicial.sql`
  - `src/prelo/db/repositorio.py`
  - `tests/conftest.py`
  - `tests/test_db.py`

### F1.1.T3 — Grafo con dobles

Usa `src/prelo/interfaces.py` y `src/prelo/estado.py` tal como los deja F1.1.T4 (no los cambies) y escribe
`src/prelo/grafo.py` con
`construir(deps, checkpointer)`, `iniciar(grafo, tema, origem) -> post_id` y `retomar(grafo, post_id, decisao,
comentario=None)`.

El flujo de F1 (sección *grafo*): `investigar → redigir → revisar`; si hay violaciones y `tentativas < 2`, vuelve a
`redigir` con el feedback; luego `adaptar_linkedin → revisar → aprovar` (`interrupt()`, con `deps.notificar` antes de
pausar) `→ agendar → END`. "editar" vuelve al adaptador con el comentario; "descartar" marca la pieza `descartada` y
va a `END`. `agendar` solo pone la pieza en `aprovada` con `decisao = aprovado`: publicar es trabajo de la agenda
(D9). `thread_id = post_id`. El grafo escribe en `posts`, `fontes` y `pecas` vía `deps.repo` (el protocolo `Repositorio`) y no importa
ningún cliente externo. Esta tarea corre en paralelo con la base de datos (F1.1.T2): en los tests usa un `Repositorio`
en memoria escrito en el propio test, y para la prueba de reinicio una fixture local que lee `TEST_DATABASE_URL` y
salta si no existe (`PostgresSaver.setup()` crea sus propias tablas; no hacen falta las migraciones).

Done when: these tests pass in `tests/test_grafo.py`, usando dobles para todas las funciones de `Dependencias` —
un tema sin violaciones llega a `aprovar` y queda pausado con la pieza `pendente`; `retomar(..., "aprovado")` deja la
pieza `aprovada` con `decisao = aprovado`; un borrador que siempre viola se reescribe exactamente 2 veces y llega a
`aprovar` con `violacoes` no vacías; "editar" llama al adaptador con el comentario y vuelve a pausar; "descartar"
deja la pieza `descartada` y no se aprueba nada; con `PostgresSaver` (fixture local sobre `TEST_DATABASE_URL`), construir un grafo nuevo
tras la pausa y aprobar con él aprueba exactamente el texto que se pausó (FR-8).

- **Model**: claude/claude-opus-4-7
- **Estimate**: 4h
- **Reason**: Flujo con interrupt/checkpointer y reintentos; diseño crítico.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/grafo.py`
  - `tests/test_grafo.py`

### F1.1.T4 — Contratos: interfaces.py y estado.py

Escribe `src/prelo/interfaces.py` y `src/prelo/estado.py` exactamente como los fija *Interfaces* de
docs/arch/001-prelo.md: `Fonte`, `Violacao`, `Texto`, `EstadoPost`, `Modelo`, `Buscador`, `Publicador`,
`Dependencias` y `Regras` (tipo opaco que rellena marca). Añade lo que el ARCH deja implícito para que las tareas
paralelas no inventen nada:
- dataclasses `Post`, `Peca`, `Publicacao` y `Custo` con los campos de *Data model*;
- un `Protocol` `Repositorio` con los métodos que usan grafo, agenda, slack y custos (crear y leer posts, guardar
  fuentes, crear/actualizar piezas, listar piezas por `status` y canal, registrar publicaciones y costos, sumar
  costos por post y agente), cada uno con su docstring;
- un `Protocol` `Aviso` (`avisar(texto: str) -> None`) para los avisos en Slack de la agenda.

Solo tipos y protocolos: ninguna implementación ni dependencia externa. Es el contrato del que parten 9 tareas en
paralelo, así que cada firma debe estar completa y documentada.

Done when: these tests pass in `tests/test_interfaces.py` — un `Repositorio` en memoria escrito en el test cumple el
protocolo (comprobado con `typing.runtime_checkable` + `isinstance`); un `EstadoPost` de ejemplo con los tres idiomas
pasa la comprobación de tipos de `pyright` o `mypy`; importar `interfaces` no importa ningún SDK externo.

- **Model**: claude/claude-opus-4-7
- **Estimate**: 1.5h
- **Reason**: Contrato del que dependen todas las tareas paralelas; un error aquí se multiplica.
- **Dependencies**: F1.1.T1
- **Files**:
  - `src/prelo/interfaces.py`
  - `src/prelo/estado.py`
  - `tests/test_interfaces.py`

## F1.2 — Package: marca

### F1.2.T1 — Revisión de marca determinista

Implementa `revisar(texto, fontes, regras) -> list[Violacao]` en `src/prelo/marca.py` según *marca* y D3/D11 de
docs/arch/001-prelo.md, y `carregar_regras(settings) -> Regras`, que junta `marca.toml` (frases de "cara de IA" y
patrones de cifras y fechas) con `settings.PRELO_BLOQUEIA`. Ningún empleador ni cliente real va en el repo (NFR-5):
los tests usan nombres inventados.

Reglas: `empregador` si aparece un nombre de la lista (sin distinguir mayúsculas ni acentos, como palabra completa);
`frase_ia` si aparece una frase de la lista de `marca.toml`; `cifra_sem_fonte` si una cifra o fecha del texto no
aparece en ningún `trecho` de las `fontes` (FR-4). Cada `Violacao` lleva el `trecho` exacto que la causó.

Done when: these tests pass in `tests/test_marca.py` — "trabajé en ACME" con `ACME` en la lista da una violación
`empregador`; "Acmé" también la da; "acmeísmo" no; una frase de la lista de `marca.toml` da `frase_ia`; "creció un
40%" sin fuente que contenga "40%" da `cifra_sem_fonte` y con ella no; "en 2024" se trata igual que una cifra; un
texto limpio devuelve lista vacía; `carregar_regras` con `PRELO_BLOQUEIA` vacío no bloquea ningún nombre.

- **Model**: claude/claude-sonnet-4-6
- **Estimate**: 3h
- **Reason**: Lógica determinista con casos borde de normalización; standard con buenos tests.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/marca.py`
  - `marca.toml`
  - `tests/test_marca.py`

## F1.3 — Package: agentes y costo

### F1.3.T1 — Modelo real, costos y Langfuse

Implementa el `Modelo` de *Interfaces* en `src/prelo/modelo.py` sobre el SDK de Anthropic, y `src/prelo/custos.py`.
Cada llamada a `gerar(prompt, agente=, post_id=)` elige el modelo por agente según D4 (fuerte para `redator`, barato
para el resto; tabla configurable en el módulo), registra tokens de entrada/salida y USD en `custos` vía el
`Repositorio` y manda la traza a Langfuse etiquetada con `post_id` y `agente` (FR-16). Las trazas y los logs nunca
incluyen tokens ni API keys (NFR-3). El cliente de Anthropic y el de Langfuse se inyectan en el constructor.

Done when: these tests pass in `tests/test_custos.py`, con clientes falsos — una llamada de `redator` usa el modelo
fuerte y una de `adaptador_linkedin` el barato; tras una llamada hay una fila en `custos` con los tokens que devolvió
el cliente y el USD calculado con la tabla de precios; la traza enviada lleva `post_id` y `agente` y su contenido
serializado no contiene el valor de la API key.

- **Model**: muse/muse-wonder-1.0
- **Estimate**: 3h
- **Reason**: Wrapper de SDK con registro de costos; patrón conocido.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/modelo.py`
  - `src/prelo/custos.py`
  - `tests/test_custos.py`

### F1.3.T2 — Buscador Tavily e investigador

Implementa el `Buscador` de *Interfaces* sobre Tavily en `src/prelo/buscador.py` (D13) y el agente `investigador` en
`src/prelo/agentes/investigador.py`: arma consultas a partir del tema con el `Modelo`, busca y devuelve `Fonte`s
deduplicadas por URL, cada una con `url`, `titulo` y `trecho` no vacíos (FR-3). El investigador no tiene ninguna
herramienta con efectos (NFR-4).

Done when: these tests pass in `tests/test_investigador.py`, con `Modelo` y cliente Tavily falsos — un tema devuelve
al menos una `Fonte` con los tres campos; dos resultados con la misma URL quedan en una sola fuente; un resultado
sin contenido se descarta; si no hay ninguna fuente, levanta un error con un motivo legible (que FR-1 muestra en
Slack).

- **Model**: agy/gemini-4-argon-medium
- **Estimate**: 2h
- **Reason**: Integración HTTP sencilla con validación.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/buscador.py`
  - `src/prelo/agentes/investigador.py`
  - `tests/test_investigador.py`

### F1.3.T3 — Redator y adaptador de LinkedIn

Implementa `redator` (`src/prelo/agentes/redator.py`) y `adaptador_linkedin`
(`src/prelo/agentes/adaptador_linkedin.py`) con las firmas de `Dependencias.redigir` y `Dependencias.adaptar` de
docs/arch/001-prelo.md. El redator escribe la pieza madre en español (`Texto`: título, resumen, cuerpo) con las
fuentes y, si llega, el feedback de violaciones o del editor. El adaptador produce el post de LinkedIn en pt-BR y,
cuando `url_blog` no es `None`, incluye ese link (FR-11). El contenido de cada fuente entra al prompt dentro de
`<fonte>…</fonte>` con la instrucción explícita de tratarlo como datos (NFR-4). Los prompts viven en el módulo de
cada agente.

Done when: these tests pass in `tests/test_redator.py`, con un `Modelo` falso que captura el prompt — cada fuente
aparece dentro de `<fonte>` y el prompt contiene la instrucción de tratarla como datos; una fuente con
"ignora las instrucciones anteriores" queda dentro del delimitador; el feedback aparece en el prompt cuando se pasa;
la salida del modelo se parsea a un `Texto` con los tres campos; el adaptador incluye `url_blog` cuando existe y no
inventa un link cuando es `None`.

- **Model**: claude/claude-sonnet-4-6
- **Estimate**: 3h
- **Reason**: Prompts y parseo; la calidad real la miden las evals de F1.6.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/agentes/redator.py`
  - `src/prelo/agentes/adaptador_linkedin.py`
  - `tests/test_redator.py`

## F1.4 — Package: slack

### F1.4.T1 — App de Slack: /prelo y aprobación

Implementa `src/prelo/slack.py` con Slack Bolt en Socket Mode (D8), según *slack* e *Interfaces → Slack* de
docs/arch/001-prelo.md. `/prelo <tema>` llama a `iniciar` (FR-1) y responde con el tema recibido o el motivo del
fallo. `notificar(peca)` publica en `SLACK_CANAL` la pieza pendiente con el texto, las fuentes (FR-3), las
violaciones, el costo del post por agente y total (FR-16) y los botones `prelo_aprovar`, `prelo_editar`,
`prelo_descartar` con `value` = JSON `{"post_id", "peca_id"}` (FR-9). Si la pieza tiene violaciones, no se muestra
"Aprobar" (FR-6). "Editar" abre un modal con el campo `comentario`. Cada acción llama a `retomar` y actualiza el
mensaje. Crea también `slack-manifest.yml` (Socket Mode, comando `/prelo`, interactividad, scopes `chat:write` y
`commands`) para crear la app una vez en api.slack.com/apps (D15). Las funciones reciben `iniciar`/`retomar` y el `Repositorio` inyectados; la app no importa el grafo.

Done when: these tests pass in `tests/test_slack.py`, con un cliente de Slack falso — `/prelo IA local` llama a
`iniciar` con ese tema; un fallo de `iniciar` responde con su motivo; el mensaje de una pieza sin violaciones trae
los tres botones con el `value` correcto, las fuentes y el costo; una pieza con violaciones no trae `prelo_aprovar`
y lista las violaciones; pulsar Aprobar llama a `retomar(post_id, "aprovado")`; enviar el modal de Editar llama a
`retomar(post_id, "editar", comentario)`; Descartar llama a `retomar(post_id, "descartar")`.

- **Model**: claude/claude-sonnet-4-6
- **Estimate**: 4h
- **Reason**: Integración Bolt con bloques y modales; varios caminos pero sin diseño nuevo.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/slack.py`
  - `slack-manifest.yml`
  - `tests/test_slack.py`

## F1.5 — Package: agenda y LinkedIn

### F1.5.T1 — Worker de agenda

Implementa `src/prelo/agenda.py` según *agenda* y D9 de docs/arch/001-prelo.md. Una función pura
`proximo_hueco(canal, ocupados, agora) -> datetime` calcula el siguiente hueco de martes a jueves con máximo una
pieza por día y canal (FR-13), con la hora de publicación configurable y zona horaria `America/Sao_Paulo`. `tick()`
(lo que corre cada minuto) toma las piezas `aprovada`, les asigna hueco, las pasa a `agendada` y avisa en Slack la
fecha; cuando llega la hora, vuelve a comprobar `decisao = aprovado` (FR-7), llama al `Publicador` del canal,
registra la `Publicacao` (FR-14) y pasa la pieza a `publicada`. Si el publicador falla, la pieza vuelve a
`aprovada` y se avisa en Slack. Avisa también 7 días antes de que caduque el token de LinkedIn (riesgo del ARCH).
Recibe publicadores, repositorio, aviso y reloj inyectados.

Done when: these tests pass in `tests/test_agenda.py` — aprobada un lunes se agenda el martes; aprobada un jueves
después de la hora se agenda el martes siguiente; con el martes ocupado en ese canal va al miércoles, pero otro canal
sí puede usar el martes; una pieza agendada cuya `decisao` no es `aprovado` no se publica; al llegar la hora se
llama al publicador y queda una `Publicacao` con canal, URL y fecha; un fallo del publicador deja la pieza
`aprovada` y genera un aviso; a 7 días de caducar el token se genera un aviso.

- **Model**: muse/muse-wonder-1.0
- **Estimate**: 4h
- **Reason**: Lógica de fechas con muchos bordes y una regla de seguridad (FR-7).
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/agenda.py`
  - `tests/test_agenda.py`

### F1.5.T2 — Publicador de LinkedIn

Implementa `src/prelo/publicadores/linkedin.py`: un `Publicador` con `canal = "linkedin"` que publica el texto de la
pieza en el perfil de Héctor con la API de LinkedIn (Posts API, `LINKEDIN_TOKEN` desde `config`) usando `httpx`, y
devuelve una `Publicacao` con la URL y el `id_externo`. No decide nada: publica lo que recibe. Un error de la API
levanta una excepción con el código y el mensaje, sin el token.

Done when: these tests pass in `tests/test_linkedin.py`, con `respx` — una publicación correcta manda el texto y el
autor esperados y devuelve una `Publicacao` con URL e `id_externo`; un 401 levanta un error que no contiene el token;
la cabecera de autorización lleva el token pero ningún log lo muestra.

- **Model**: agy/gemini-4-argon-medium
- **Estimate**: 2h
- **Reason**: Cliente HTTP acotado.
- **Dependencies**: F1.1.T4
- **Files**:
  - `src/prelo/publicadores/linkedin.py`
  - `tests/test_linkedin.py`

## F1.6 — Package: evals

### F1.6.T1 — Evals de estilo, fidelidad y marca en CI

Crea `evals/` según *evals* y NFR-2 de docs/arch/001-prelo.md: un runner (`evals/run.py`) que descubre cada
subdirectorio de `evals/` como un conjunto de casos fijos (tema + fuentes + salida esperada o criterios), ejecuta el
agente correspondiente y calcula métricas con umbral: fidelidad a las fuentes (LLM juez barato), estilo (LLM juez con
rúbrica) y violaciones de marca (`revisar`, umbral 0). El runner sale con código distinto de 0 si una métrica queda
bajo su umbral. Incluye al menos 5 casos para `redator` + `adaptador_linkedin`. `.github/workflows/evals.yml` lo
corre en cada PR con los secretos del repo. El runner deja el costo de la corrida en la salida.

Done when: these tests pass in `evals/test_runner.py`, con agentes y juez falsos — una métrica sobre el umbral sale
con código 0; una bajo el umbral sale con código 1 y nombra la métrica; una violación de marca en cualquier caso hace
fallar la corrida; el runner descubre un subdirectorio nuevo sin tocar su código.

- **Model**: muse/muse-wonder-1.0
- **Estimate**: 4h
- **Reason**: Diseño de métricas y juez; standard con criterio.
- **Dependencies**: F1.2.T1, F1.3.T1, F1.3.T3
- **Files**:
  - `evals/run.py`
  - `evals/test_runner.py`
  - `evals/linkedin/`
  - `.github/workflows/evals.yml`

## F1.7 — Package: conexión

### F1.7.T1 — app.py, API de salud y README

Conecta todo según *Components* de docs/arch/001-prelo.md. `src/prelo/app.py` lee `Settings`, aplica las
migraciones, construye los clientes reales, arma las `Dependencias` (investigador, redator, adaptador LinkedIn,
`revisar` con `carregar_regras`, `notificar` de Slack, repositorio), construye el grafo con `PostgresSaver` y arranca
en un solo proceso la API, la app de Slack y el worker de agenda (cada minuto). `src/prelo/api.py` es FastAPI con
`GET /saude` (200 si la base responde) y `POST /posts` para Hermes según *Interfaces → API para Hermes* y D15
(`{"tema"}` + `Bearer PRELO_API_TOKEN` → `202 {"post_id"}`; comparación del token en tiempo constante). No existe
ningún endpoint que apruebe. Reemplaza `README.md` por uno que explique qué es Prelo, el diagrama del
grafo, cómo levantarlo con `docker compose up`, cómo crear la app de Slack desde `slack-manifest.yml`, cómo apuntar Hermes a
`POST /posts` y qué variables hacen falta.

Done when: these tests pass in `tests/test_app.py` — `GET /saude` responde 200 con la base disponible y 503 sin
ella; `POST /posts` con el token correcto llama a `iniciar` y responde 202 con el `post_id`; sin token o con
uno incorrecto responde 401 y no llama a `iniciar`; un tema vacío responde 422; `montar_dependencias(settings, clientes_falsos)` devuelve unas `Dependencias` con todas sus claves y el
adaptador `linkedin`; con dobles, un `/prelo` simulado termina en una pieza pendiente notificada en Slack.

- **Model**: claude/claude-sonnet-4-6
- **Estimate**: 4h
- **Reason**: Cableado de piezas ya probadas más un endpoint autenticado.
- **Dependencies**: F1.1.T2, F1.1.T3, F1.2.T1, F1.3.T1, F1.3.T2, F1.3.T3, F1.4.T1, F1.5.T1, F1.5.T2
- **Files**:
  - `src/prelo/app.py`
  - `src/prelo/api.py`
  - `tests/test_app.py`
  - `README.md`
