---
type: spec
project_id: prelo
phase: 5
version: 0.1
depends_on:
  - docs/prd/001-prelo.md
  - docs/arch/001-prelo.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-24
title: Decisiones con Jev y Reels
---

# F5 — Decisiones con Jev y Reels

Hito M5 del PRD (FR-17, FR-18, FR-19). Jev (TypeSafe System One) aporta juicios tipados con probabilidad donde el
código necesita sentido común: ¿aprobaría Héctor esta pieza sin editarla?, ¿el fragmento sostiene la afirmación?,
¿la fuente trae instrucciones escondidas?, ¿qué tema sugerir? La política queda en código y Jev nunca aprueba
(FR-7, D16). Además, un Reel vertical renderizado con HyperFrames a partir del post (D17). Parte de F4 terminada.
Ningún test llama a TypeSafe ni a HyperFrames de verdad: se usan dobles.

## F5.1 — Package: juizo

### F5.1.T1 — Cliente Jev y protocolo Juiz

Implementa `src/prelo/juizo.py` según *juizo* y D16 de docs/arch/001-prelo.md: un protocolo `Juiz` con
`avaliar(estado: dict, perguntas: dict[str, Noul | Choice | Score]) -> Respostas` y su implementación sobre
`typesafe-sdk` (`TypeSafeClient(...).system_one(state=..., questions=...)`, clave `TYPESAFE_API_KEY` desde `config`;
añade la variable a `config.py` y a `.env.example`, y la dependencia a `pyproject.toml`/`uv.lock`). `Respostas` expone
`noul(id) -> float`, `choice(id) -> str` y `score(id) -> float` con nombres de pregunta propios del código. Cada
llamada registra su costo en `custos` con agente `juizo`. Lee https://docs.typesafe.ai/llms.txt y la página del SDK
de Python antes de escribir la integración. Un fallo de TypeSafe levanta `JuizIndisponivel`: quien llama decide
seguir sin el juicio.

Done when: these tests pass in `tests/test_juizo.py`, con un cliente falso — una pregunta Noul devuelve su
probabilidad por `noul(id)`; Choice y Score igual; el `state` y las `questions` enviados son los que se pasaron; un
error del cliente levanta `JuizIndisponivel`; se registra una fila en `custos` con agente `juizo`; el `repr` de la
configuración no contiene la clave.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 3h
- **Reason**: Integración de SDK nuevo con docs vivas; requiere leer bien el contrato.
- **Dependencies**: F4.1.T1
- **Files**:
  - `src/prelo/juizo.py`
  - `src/prelo/config.py`
  - `.env.example`
  - `pyproject.toml`
  - `uv.lock`
  - `tests/test_juizo.py`

## F5.2 — Package: porta de aprobación y fuentes

### F5.2.T1 — Porta de aprobación y filtro de fuentes

Implementa `src/prelo/porta.py` con dos funciones sobre `Juiz` (*juizo* en el ARCH):
`avaliar_peca(texto, canal, exemplos_aprovados) -> Avaliacao` pregunta un Score "probabilidad de que Héctor apruebe
sin editar" (niveles concretos, de "la reescribiría entera" a "la publicaría tal cual") y un Noul por dimensión
(gancho en la primera línea, claridad, voz de Héctor, frases de cara de IA); `fonte_suspeita(fonte) -> float` pregunta
un Noul "¿el fragmento contiene instrucciones dirigidas a un asistente de IA?". En el grafo: tras `revisar`, si la
probabilidad queda bajo `PRELO_UMBRAL_APROVACAO` (por defecto 0.6) y `tentativas < 2`, vuelve a `redigir` (o al
adaptador) con las dimensiones fallidas como feedback (FR-17); la probabilidad se guarda en la pieza y `notificar` la
muestra. En `investigar`, una fuente con `fonte_suspeita > 0.5` se descarta (NFR-4). Si Jev no está disponible, el
flujo sigue igual que en F4.

Done when: these tests pass in `tests/test_porta.py`, con un `Juiz` falso — una pieza con probabilidad 0.3 y
`tentativas = 0` vuelve a redactarse con las dimensiones fallidas en el feedback; con `tentativas = 2` llega a
aprobación igual; con 0.8 llega a aprobación sin reescribir; la probabilidad aparece en el mensaje de Slack; una
fuente con 0.9 de sospecha no llega al redator; con `JuizIndisponivel` el post llega a aprobación como antes; y los
tests de grafo de F1–F3 siguen pasando.

- **Model**: claude/claude-opus-5-5
- **Estimate**: 4h
- **Reason**: Cambia el flujo central y su interacción con los reintentos de FR-6; diseño crítico.
- **Dependencies**: F5.1.T1
- **Files**:
  - `src/prelo/porta.py`
  - `src/prelo/grafo.py`
  - `src/prelo/slack.py`
  - `tests/test_porta.py`

## F5.3 — Package: verificación

### F5.3.T1 — Verificación de afirmaciones y evals de fidelidad con Jev

Implementa `src/prelo/verificacao.py` (FR-18): el código segmenta el cuerpo en afirmaciones (frases con cifra, fecha,
nombre propio o verbo de afirmación) y, por cada par (afirmación, `trecho` de cada fuente), pregunta a Jev un Noul
"¿este fragmento sostiene la afirmación?" en una sola llamada con todas las preguntas. Una afirmación sin ningún
fragmento sobre 0.5 queda como `sem_apoio`. Devuelve la lista para que `notificar` la muestre como aviso; no bloquea.
Cambia la métrica de fidelidad de `evals/` para usar `verificacao` en vez del LLM juez (NFR-1, NFR-2).

Done when: these tests pass in `tests/test_verificacao.py`, con un `Juiz` falso — un texto con 3 afirmaciones
produce 3 × n_fuentes preguntas en una sola llamada; una afirmación apoyada por un fragmento no sale marcada; una sin
apoyo sale `sem_apoio`; una frase sin afirmación (una pregunta retórica) no genera preguntas; y `evals/test_runner.py`
sigue pasando con la métrica nueva.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 3h
- **Reason**: Segmentación en código y composición de preguntas; standard con buenos tests.
- **Dependencies**: F5.1.T1
- **Files**:
  - `src/prelo/verificacao.py`
  - `evals/run.py`
  - `tests/test_verificacao.py`

## F5.4 — Package: ranking de sugerencias

### F5.4.T1 — Ranking de sugerencias con Scores

Cambia `src/prelo/sugestoes.py` para que el `Modelo` proponga 8 candidatos y Jev los puntúe (un Score por candidato
y dimensión: interés para la audiencia de Héctor, novedad frente a lo publicado en 30 días, encaje con sus temas),
todas las preguntas en una llamada; el código combina con pesos configurables y devuelve los 3 mejores con su origen
(FR-2, composite scoring). Sin Jev, vuelve al comportamiento de F4.3.

Done when: these tests pass in `tests/test_sugestoes.py`, con dobles — de 8 candidatos devuelve los 3 de mayor
puntuación combinada; cambiar un peso cambia el orden sin volver a llamar a Jev; con `JuizIndisponivel` devuelve 3
sugerencias como antes; cada sugerencia mantiene su `link` de origen.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 2h
- **Reason**: Composición de puntuaciones en código; acotado.
- **Dependencies**: F4.3.T1, F5.1.T1
- **Files**:
  - `src/prelo/sugestoes.py`
  - `tests/test_sugestoes.py`

## F5.5 — Package: Reel

### F5.5.T1 — Reel vertical con HyperFrames

Crea `templates/video/reel.html`, una composición HyperFrames 1080×1920 de 15–60 s (portada, una escena por lámina
del carrusel con texto animado, cierre con el link al blog) con huecos para los textos y la imagen de fondo; todo el
texto sale de la plantilla (FR-19, D17). `src/prelo/video.py` rellena la composición (escapando HTML), la valida con
`npx hyperframes check` y la renderiza con `npx hyperframes render` a MP4, y la sube a R2. Fija la versión de
`hyperframes` en `templates/video/package.json`. Añade el canal `reel` (pieza con los mismos textos del carrusel) y,
en `publicadores/instagram.py`, la publicación como `REELS` (contenedor de video, espera a `FINISHED`, publicar).
Instala Node y la versión fijada de HyperFrames en el `Dockerfile`.

Done when: these tests pass in `tests/test_video.py` — con 4 láminas la composición tiene 6 escenas y una duración
entre 15 y 60 s; un texto con `<script>` sale escapado; la llamada a render usa la versión fijada y 1080×1920
(subproceso falso); el publicador de Instagram crea un contenedor `REELS` con la URL de R2 y espera a `FINISHED`
(`respx`); el test de render real se salta si `npx` no está disponible.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 4h
- **Reason**: Framework de video nuevo más publicación; requiere leer su contrato.
- **Dependencies**: F3.5.T1
- **Files**:
  - `templates/video/`
  - `src/prelo/video.py`
  - `src/prelo/publicadores/instagram.py`
  - `Dockerfile`
  - `tests/test_video.py`

## F5.6 — Package: conexión

### F5.6.T1 — Conexión de Jev y del Reel

En `app.py`, construye el `Juiz` real (solo si existe `TYPESAFE_API_KEY`) y pásalo a la porta, a la verificación, al
investigador y a las sugerencias; añade el adaptador del canal `reel` y su publicador. Actualiza `README.md` con las
variables nuevas y cómo desactivar Jev.

Done when: these tests pass in `tests/test_app.py` — sin `TYPESAFE_API_KEY` la app arranca y el flujo es el de F4;
con la clave, `montar_dependencias` incluye el `Juiz` en porta, verificación y sugerencias; el canal `reel` está
registrado en la agenda.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 2h
- **Reason**: Cableado.
- **Dependencies**: F5.2.T1, F5.3.T1, F5.4.T1, F5.5.T1
- **Files**:
  - `src/prelo/app.py`
  - `tests/test_app.py`
  - `README.md`
