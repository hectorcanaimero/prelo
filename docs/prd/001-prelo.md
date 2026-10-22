# PRD 001 · Prelo

> *No prelo*: a punto de publicarse.

## Problema

Héctor quiere publicar con constancia sobre lo que construye y estudia (agentes, LLMs, infraestructura) en tres canales:
el blog [guria.lat/blog](https://www.guria.lat/blog) (es/pt/en), LinkedIn e Instagram. Hoy:

- LinkedIn ya funciona con propuestas diarias y aprobación en Slack, pero es un flujo aislado.
- El blog es Astro estático: publicar significa escribir MDX en tres idiomas y hacer deploy a mano.
- Instagram no existe todavía.
- No hay una fuente única: cada canal se escribe desde cero, sin medir costo ni calidad.

## Objetivo

Una mesa editorial de agentes que convierte **una idea** en **una pieza madre** (post del blog en es/pt/en) y en
**derivados** por canal (LinkedIn, carrusel de Instagram), con **aprobación humana** antes de publicar y
**métricas de costo y calidad** visibles.

Es también un proyecto de portafolio público: debe mostrar LangGraph, evals, observabilidad y deploy en la nube.

## Usuario

Héctor (único editor). Aprueba desde Slack (canal de publicación) y desde GitHub (merge del PR del blog).

## Flujo

1. **Tema**: lo propone Héctor, o Prelo sugiere 3 a partir de commits recientes, la ruta de estudio o noticias de IA.
2. **Investigación**: fuentes con URL; toda cifra lleva fuente.
3. **Pieza madre**: post del blog en español; traducción/adaptación a pt-BR y en.
4. **Revisión de marca** (determinista): bloquea empleadores, cifras sin fuente y frases con cara de IA.
5. **Aprobación del blog**: Prelo abre un PR en `site-guria` con los tres MDX. El merge es el "sí".
6. **Derivados**: tras el deploy, post de LinkedIn (pt-BR) y carrusel de Instagram, con link al blog.
7. **Aprobación de derivados** en Slack: Aprobar / Editar / Descartar.
8. **Publicación y métricas**: registro de lo publicado; reacciones y comentarios vuelven al sistema.

## Requisitos

### Funcionales
- R1. Un post puede esperar días una aprobación sin perder estado.
- R2. El MDX generado pasa el schema de la colección `blog` de Astro (el CI del sitio lo valida).
- R3. Nunca se publica sin aprobación explícita.
- R4. Ningún texto publicado contiene nombres de empleadores o clientes (lista en `marca.toml`).
- R5. Cada cifra o fecha en el texto tiene una fuente en el estado del post.
- R6. Máximo 1 publicación por día por canal; franjas de martes a jueves.
- R7. Las imágenes de IA no contienen texto; el texto de los carruseles sale de plantillas HTML.

### No funcionales
- Costo por post visible (tokens y USD por agente) en Langfuse.
- Evals en CI: fidelidad a fuentes, estilo, calidad de traducción, 0 violaciones de marca.
- Reproducible con `docker compose up`.

## Fuera de alcance (v1)
- Múltiples usuarios o marcas.
- Edición visual del post (se edita en el PR o se pide el cambio en Slack).
- Leer impresiones de LinkedIn (la API no lo permite con el permiso actual).

## Entregas
- **v0**: esqueleto, grafo con aprobación, revisión de marca, CI. *(este commit)*
- **v1**: LinkedIn de punta a punta en el grafo + aprobación en Slack + Langfuse + evals de estilo.
- **v2**: blog como pieza madre: MDX es/pt/en y PR en `site-guria`.
- **v3**: carruseles e Instagram (Graph API, imágenes en R2).
- **v4**: bucle de métricas, servidor MCP, deploy en AWS con Terraform.

## Métricas de éxito
- 3 posts por semana publicados con Prelo durante un mes.
- Costo medio por post (los 3 canales) bajo USD 0,50.
- 0 violaciones de marca publicadas.
- % de borradores aprobados sin edición, en aumento.

## Preguntas abiertas
- ¿Cómo se despliega hoy `site-guria`? (necesario para v2: workflow de deploy al merge)
- Cuenta de Instagram: Business o Creator, personal o de marca.
- ¿Las fichas de `src/content/internos/` pueden seguir públicas?
