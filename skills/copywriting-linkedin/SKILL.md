---
name: copywriting-linkedin
description: Escribe o reescribe un post técnico de LinkedIn en pt-BR, en primera persona, a partir de una pieza del blog. Úsala para la apertura, el cuerpo y la pregunta final. Los límites medibles (palabras, emojis, hashtags) vienen de marca.toml; la voz, de voz-hector.
license: Adaptada de coreyhaines31/marketingskills (skills/copywriting), vía la adaptación de agno-content. Ver ATTRIBUTION.md.
---

# Copywriting para LinkedIn técnico (pt-BR)

Escribes un post de LinkedIn para un ingeniero que construye con IA. El post va
en portugués de Brasil y en primera persona. No es un resumen de la pieza del
blog: es una idea de esa pieza contada por quien la vivió.

## Principios

- **Una idea.** Elige la idea más fuerte o más discutible de la pieza y descarta
  el resto, aunque sea bueno. Un post que cubre todo no deja nada para comentar.
- **Experiencia antes que documentación.** "Cuando lo puse en producción vi
  que…" vale más que explicar cómo funciona la herramienta. Si la pieza no trae
  una experiencia propia, cuenta la decisión o el criterio, no el manual.
- **Específico antes que vago.** "Una generation por llamada al modelo" y no
  "buenas prácticas de observabilidad". Nombra la herramienta, el número, el error.
- **Claridad antes que ingenio.** Si hay que elegir entre claro y creativo, claro.
- **Honestidad.** No inventes cifras, clientes, resultados ni anécdotas. Si
  falta un dato, escribe una frase más simple.

## Estructura (la de los posts de Héctor: una idea por línea, sin párrafos largos)

1. **Primera línea:** la tesis en una frase contundente de menos de 15 palabras.
   Es lo único que se ve antes del "ver más". Sin preguntas retóricas de
   apertura ni "Você já parou para pensar…".
2. **El hecho:** qué pasó o qué es, con su fuente y su fecha cuando la hay
   ("O dado é do…, publicado em 15/10"). Uno o dos datos concretos, no más.
3. **"Minha posição:"** el criterio de Héctor en una o dos frases, y si aplica,
   cómo lo hace él (orch, Prelo, su stack).
4. **Remate opcional:** una frase corta que cierra la idea ("Vazamento com
   limite é incidente. Sem limite, é fatura.").
5. **Pregunta:** concreta, que alguien del área pueda responder desde su
   experiencia ("Vocês registram uma generation por chamada ou agregam?"),
   no genérica ("O que vocês acham?").
6. **Hashtags:** al final, en su propia línea.

## Estilo

1. Texto plano: sin negritas, títulos ni listas con viñetas o emojis.
2. Voz activa y frases de largo variado.
3. Términos técnicos en inglés como se usan en el área (trace, eval, prompt,
   generation); no los traduzcas a la fuerza.
4. Sin exclamaciones ni superlativos vacíos ("incrível", "revolucionário").

## Revisión rápida antes de entregar

- ¿La primera línea se entiende sola y dan ganas de seguir?
- ¿Hay una sola idea, o se coló un segundo tema?
- ¿Hay algo que solo Héctor podría haber escrito (una decisión, un error, un número)?
- ¿La pregunta final se puede responder con experiencia propia?
- ¿Algún dato sin fuente? Quítalo.

Después de escribir, aplica la skill `humanizer`.
