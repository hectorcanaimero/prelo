---
type: prd
project_id: prelo
version: 0.2
generated_by: orch-prd
generated_at: 2026-10-23
title: Prelo
---

# Prelo

> *No prelo*: a punto de publicarse.

## Problem

Héctor quiere publicar con constancia sobre lo que construye y estudia (agentes, LLMs, infraestructura) en tres
canales: el blog [guria.lat/blog](https://www.guria.lat/blog) (es/pt/en), LinkedIn e Instagram.

Hoy cada canal va por su lado. LinkedIn tiene propuestas diarias con aprobación en Slack, pero es un flujo aislado.
Publicar en el blog significa escribir el MDX en tres idiomas y hacer el deploy a mano. Instagram todavía no existe.
No hay una fuente única: cada pieza se escribe desde cero y no se mide ni el costo ni la calidad.

El resultado es que se publica poco y de forma irregular, y el mismo trabajo de investigación se hace una vez por
canal.

## Users

- **Héctor (editor único)**: propone o elige temas, revisa borradores y aprueba o rechaza cada publicación desde
  Slack y desde GitHub (merge del PR del blog).
- **Lectores del blog, LinkedIn e Instagram**: leen las piezas; no interactúan con Prelo directamente.
- **Quien revisa el portafolio** (reclutadores, clientes): lee el repo público para evaluar cómo está construido.

## Goals

- G1 — 3 posts por semana publicados con Prelo durante un mes seguido.
- G2 — Costo medio por post (los tres canales) bajo USD 0,50.
- G3 — 0 violaciones de marca publicadas.
- G4 — El porcentaje de borradores aprobados sin edición sube mes a mes.
- G5 — El repo público muestra un grafo de agentes con aprobación humana, evals, observabilidad y deploy en la nube.

## Non-goals

- Varios usuarios o marcas: hay un solo editor y una sola voz.
- Edición visual del post: se edita en el PR o se pide el cambio en Slack.
- Leer impresiones de LinkedIn: la API no lo permite con el permiso actual.
- Publicar sin intervención humana, aunque el borrador pase todas las revisiones.

## Functional requirements

- **FR-1** — Héctor inicia un post enviando un tema por Slack. *Acceptance:* tras enviar un tema, aparece en Slack un
  borrador asociado a ese tema, o el motivo por el que no se pudo generar.
- **FR-2** — A pedido, Prelo sugiere 3 temas a partir de commits recientes, la ruta de estudio o noticias de IA.
  *Acceptance:* cada sugerencia indica su origen con un link (commit, documento o noticia), y elegir una inicia un
  post como en FR-1.
- **FR-3** — Cada post guarda las fuentes que usó. *Acceptance:* cada post tiene al menos una fuente con URL, título
  y fragmento citado, y Héctor puede verlas junto al borrador.
- **FR-4** — Toda cifra o fecha del texto tiene una fuente registrada en el post. *Acceptance:* un borrador con una
  cifra sin fuente no puede aprobarse sin edición (ver FR-6).
- **FR-5** — Prelo escribe la pieza madre en español y la adapta a pt-BR y en. *Acceptance:* un post aprobado tiene
  título, resumen y cuerpo en los tres idiomas.
- **FR-6** — Una revisión de marca bloquea: nombres de empleadores o clientes de una lista privada, cifras sin fuente
  y frases de una lista de "cara de IA". Si encuentra un bloqueo, Prelo reescribe el borrador hasta 2 veces; si sigue
  fallando, lo entrega a aprobación con las violaciones visibles. *Acceptance:* un borrador con el nombre de un
  empleador de la lista nunca llega publicado, y uno que sigue con violaciones no tiene la opción "Aprobar" sin
  editarlo antes.
- **FR-7** — Nada se publica sin una aprobación explícita de Héctor. *Acceptance:* en ningún camino del flujo se
  publica en un canal sin una decisión "aprobado" registrada para esa pieza y ese canal.
- **FR-8** — Un post puede esperar días a la aprobación sin perder estado. *Acceptance:* si el servicio se reinicia
  mientras un post espera, aprobarlo después publica exactamente el borrador que se aprobó.
- **FR-9** — En Slack, cada pieza pendiente ofrece Aprobar, Editar (con un comentario) y Descartar. *Acceptance:*
  Editar produce un borrador nuevo que tiene en cuenta el comentario y vuelve a pedir aprobación; Descartar cierra el
  post sin publicar nada.
- **FR-10** — El post del blog se aprueba como un PR en `site-guria` con los tres MDX; el merge es la aprobación.
  *Acceptance:* el PR pasa el check de schema de la colección `blog` en el CI del sitio, y tras el merge el post queda
  publicado en guria.lat/blog en los tres idiomas.
- **FR-11** — Prelo genera un post de LinkedIn en pt-BR a partir del tema. Cuando existe el post del blog, el de
  LinkedIn se genera después de su deploy e incluye el link. *Acceptance:* el post de LinkedIn aprobado aparece en el
  perfil de Héctor y, si hay blog, enlaza a la URL publicada.
- **FR-12** — Prelo genera un carrusel de Instagram con link al blog. El texto del carrusel sale de plantillas; las
  imágenes generadas por IA no llevan texto. *Acceptance:* el carrusel aprobado aparece en la cuenta de Instagram y
  ninguna imagen generada contiene texto.
- **FR-13** — Se publica como máximo una pieza por día y por canal, solo de martes a jueves. *Acceptance:* una pieza
  aprobada fuera de esa franja, o con el cupo del día ya usado, se publica en el siguiente hueco libre y Slack informa
  la fecha.
- **FR-14** — Prelo registra todo lo publicado. *Acceptance:* por cada publicación se puede ver canal, URL y fecha.
- **FR-15** — Las reacciones y los comentarios de LinkedIn e Instagram vuelven a Prelo. *Acceptance:* para cada
  publicación se ven sus reacciones y comentarios, actualizados al menos una vez al día.
- **FR-16** — El costo de cada post es visible. *Acceptance:* para cada post se ven los tokens y el costo en USD por
  agente y en total.

## Non-functional requirements

- **NFR-1** — Costo medio por post, contando los tres canales, bajo USD 0,50.
- **NFR-2** — Evals en CI: fidelidad a las fuentes, estilo, calidad de traducción y 0 violaciones de marca. Un PR que
  baja una métrica por debajo de su umbral no se puede mergear.
- **NFR-3** — Los tokens de GitHub, LinkedIn, Instagram y Slack nunca aparecen en el estado del post, en los logs ni
  en las trazas.
- **NFR-4** — El contenido de fuentes externas se trata como no confiable: una instrucción escondida en una fuente no
  cambia el comportamiento de Prelo.
- **NFR-5** — La lista de empleadores y clientes bloqueados nunca se guarda en el repo público.
- **NFR-6** — Todo el sistema se levanta en local con `docker compose up`.
- **NFR-7** — *Restricción (portafolio):* el grafo de agentes usa LangGraph, la observabilidad usa Langfuse y el
  deploy en la nube es en AWS con Terraform.
- **NFR-8** — *Restricción (blog):* el blog es el sitio Astro estático `site-guria`; Prelo solo entrega MDX que cumple
  el schema de su colección `blog`.

## Assumptions

- El código de la v0 se borró del repo el 2026-10-23. Los hitos empiezan de cero; el commit `73e0a22` queda como
  referencia, no como base.
- Una pieza aprobada fuera de la franja de FR-13 se encola para el siguiente hueco, no se rechaza.
- En M1 el post de LinkedIn sale sin blog y sin link; desde M2 se genera después del deploy del blog.
- Slack es el único canal de aprobación de los derivados; el blog se aprueba solo con el merge del PR.
- La lista de frases con "cara de IA" la mantiene Héctor y puede ser pública; la de empleadores, no (NFR-5).

## Open questions

- *Resuelta (2026-10-24):* el flujo de LinkedIn de Hermes en Slack lo reemplaza Prelo en M1; Hermes puede seguir
  pidiendo posts a Prelo, pero no aprueba (ver D15 del ARCH).

- ¿Cómo se despliega hoy `site-guria`? Hace falta para M2 (deploy al hacer merge). — Héctor.
- Cuenta de Instagram: ¿Business o Creator, personal o de marca? Hace falta para M3. — Héctor.
- ¿Las fichas de `src/content/internos/` del sitio pueden seguir públicas? — Héctor.
- El servidor MCP de la entrega v4 original, ¿quién lo usa y qué expone? Sin respuesta queda fuera de los hitos. —
  Héctor.

## Milestones

- M1 — LinkedIn de punta a punta con aprobación en Slack: FR-1, FR-3, FR-4, FR-6, FR-7, FR-8, FR-9, FR-11, FR-13,
  FR-14, FR-16
- M2 — El blog como pieza madre (es/pt/en por PR) y LinkedIn enlazado: FR-5, FR-10, FR-11
- M3 — Carrusel de Instagram: FR-12
- M4 — Bucle de métricas, sugerencia de temas y Prelo en la nube: FR-2, FR-15, NFR-7
