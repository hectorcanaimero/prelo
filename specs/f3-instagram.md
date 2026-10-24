---
type: spec
project_id: prelo
phase: 3
version: 0.1
depends_on:
  - docs/prd/001-prelo.md
  - docs/arch/001-prelo.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-24
title: Carrusel de Instagram
---

# F3 — Carrusel de Instagram

Hito M3 del PRD (FR-12). Tras el deploy del blog, Prelo genera un carrusel con textos de plantilla e imágenes de
fondo sin texto, se aprueba en Slack y se publica en Instagram. La cuenta de Instagram es una pregunta abierta del
PRD: el publicador real se prueba con dobles y se activa cuando exista la cuenta.

## F3.1 — Package: esqueleto del carrusel

### F3.1.T1 — Nodo adaptar_carrossel y canal instagram con dobles

Añade el derivado `instagram` al grafo según *grafo* de docs/arch/001-prelo.md: tras `esperar_deploy`, además de
LinkedIn, `adaptar_carrossel → revisar → aprovar` crea una pieza de canal `instagram` con `conteudo` =
`{"laminas": [{"titulo", "texto"}], "prompt_imagem": str, "url_blog": str}` y pasa por la misma aprobación en Slack.
Añade al `pyproject.toml` las dependencias de la fase (`playwright`, `openai`, `boto3`) y regenera `uv.lock`, para
que las tareas paralelas no toquen esos archivos. Comprueba que `slack.notificar` muestra una pieza `instagram`
(texto de cada lámina) y que la agenda la trata como un canal más (FR-13).

Done when: these tests pass in `tests/test_grafo_carrossel.py`, con dobles — tras el deploy hay dos piezas
pendientes, `linkedin` e `instagram`; aprobar una no aprueba la otra; descartar el carrusel no afecta a LinkedIn; la
revisión de marca se aplica al texto de todas las láminas; y los tests de F1 y F2 siguen pasando.

- **Model**: claude/claude-sonnet-4-6
- **Estimate**: 3h
- **Reason**: Extiende un patrón ya fijado en F2.1; standard basta.
- **Dependencies**: F2.5.T1
- **Files**:
  - `src/prelo/grafo.py`
  - `src/prelo/estado.py`
  - `pyproject.toml`
  - `uv.lock`
  - `tests/test_grafo_carrossel.py`

## F3.2 — Package: render

### F3.2.T1 — Plantillas HTML y PNG con Playwright

Crea `templates/carrossel/` con una plantilla de portada, una de lámina y una de cierre (con el link al blog), con
los huecos `{{titulo}}`, `{{texto}}`, `{{imagem_url}}`, `{{n}}/{{total}}` de *Interfaces → Plantillas de carrusel*.
`src/prelo/carrossel.py` rellena las plantillas (escapando HTML) y las pasa a PNG 1080×1350 con Playwright Chromium
headless (D5). Las plantillas no cargan nada de internet salvo `imagem_url`.

Done when: these tests pass in `tests/test_carrossel.py` — 3 láminas producen 3 PNG de 1080×1350; un texto con
`<script>` sale escapado en el HTML; `{{n}}/{{total}}` se rellena como `2/3`; la última lámina lleva el link al blog;
el test se salta si Chromium no está instalado.

- **Model**: agy/gemini-3.1-pro-high
- **Estimate**: 3h
- **Reason**: HTML/CSS y render con Playwright; standard.
- **Dependencies**: F3.1.T1
- **Files**:
  - `templates/carrossel/`
  - `src/prelo/carrossel.py`
  - `tests/test_carrossel.py`

## F3.3 — Package: imágenes y R2

### F3.3.T1 — Imagen de fondo y subida a R2

Implementa `src/prelo/imagens.py` con `gerar_imagem(prompt) -> bytes` sobre `gpt-image-1` (D14): añade siempre al
prompt la instrucción de no incluir texto, letras ni números (FR-12), y registra el costo en `custos` con agente
`imagem`. Implementa `src/prelo/r2.py` con `subir(nome, dados, tipo) -> url` sobre R2 (S3 compatible, `boto3`,
variables `R2_*`). Los clientes se inyectan.

Done when: these tests pass in `tests/test_imagens.py`, con clientes falsos — el prompt enviado contiene la
prohibición de texto aunque el prompt de entrada no la tenga; se registra una fila en `custos` con agente `imagem`;
`subir` devuelve una URL pública con el nombre dado; un error del cliente de imágenes levanta un error legible.

- **Model**: muse/muse-wonder-1.0
- **Estimate**: 2h
- **Reason**: Dos clientes de SDK acotados.
- **Dependencies**: F3.1.T1
- **Files**:
  - `src/prelo/imagens.py`
  - `src/prelo/r2.py`
  - `tests/test_imagens.py`

### F3.3.T2 — Agente adaptador_carrossel

Implementa `src/prelo/agentes/adaptador_carrossel.py` con la firma de `Dependencias.adaptar`: a partir del `Texto`
en pt-BR y `url_blog` produce entre 4 y 8 láminas (`titulo` ≤ 60 caracteres, `texto` ≤ 220) y un `prompt_imagem`
descriptivo sin texto, con el modelo barato (D4). Las fuentes van delimitadas como en F1.3.T3 (NFR-4).

Done when: these tests pass in `tests/test_adaptador_carrossel.py`, con un `Modelo` falso — devuelve entre 4 y 8
láminas; un título de más de 60 caracteres se rechaza y se pide de nuevo una vez; el `url_blog` va en la última
lámina; con `feedback` el comentario aparece en el prompt.

- **Model**: agy/gemini-3.8-flash-medium
- **Estimate**: 2h
- **Reason**: Prompt y validación de longitudes; tarea mecánica.
- **Dependencies**: F3.1.T1
- **Files**:
  - `src/prelo/agentes/adaptador_carrossel.py`
  - `tests/test_adaptador_carrossel.py`

## F3.4 — Package: Instagram

### F3.4.T1 — Publicador de Instagram

Implementa `src/prelo/publicadores/instagram.py`: un `Publicador` con `canal = "instagram"` que publica un carrusel
con la Instagram Graph API (`IG_TOKEN`, `IG_USER_ID`) vía `httpx`: crea un contenedor por imagen (URL de R2), el
contenedor `CAROUSEL` con el pie de foto, espera a que esté `FINISHED` y lo publica. Devuelve una `Publicacao` con
permalink e `id_externo`. Ningún error ni log contiene el token.

Done when: these tests pass in `tests/test_instagram.py`, con `respx` — 3 imágenes generan 3 contenedores hijos y uno
`CAROUSEL` con sus ids; se espera al estado `FINISHED` antes de publicar; devuelve permalink e `id_externo`; un
contenedor en `ERROR` levanta un error sin el token.

- **Model**: muse/muse-wonder-1.0
- **Estimate**: 3h
- **Reason**: API de varios pasos con espera de estado.
- **Dependencies**: F3.1.T1
- **Files**:
  - `src/prelo/publicadores/instagram.py`
  - `tests/test_instagram.py`

## F3.5 — Package: conexión

### F3.5.T1 — Conexión del carrusel

Añade a `montar_dependencias` el adaptador `instagram`. Al aprobarse una pieza `instagram`, antes de agendarla, genera
la imagen de fondo, renderiza las láminas, sube los PNG a R2 y guarda sus URLs en `conteudo`. Registra el publicador
de Instagram en la agenda solo si `IG_TOKEN` existe; sin él, la pieza queda `aprovada` y Slack avisa. Instala
Chromium de Playwright en el `Dockerfile`.

Done when: these tests pass in `tests/test_app.py` — `montar_dependencias` incluye el adaptador `instagram`; con
dobles, aprobar un carrusel deja en `conteudo` una URL de R2 por lámina; sin `IG_TOKEN` la agenda no registra el
publicador de Instagram. Además `docker build` termina y `playwright` encuentra Chromium dentro de la imagen.

- **Model**: claude/claude-sonnet-4-6
- **Estimate**: 3h
- **Reason**: Cableado más un paso de preparación con varios servicios.
- **Dependencies**: F3.2.T1, F3.3.T1, F3.3.T2, F3.4.T1
- **Files**:
  - `src/prelo/app.py`
  - `Dockerfile`
  - `tests/test_app.py`
