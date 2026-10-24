---
type: spec
project_id: prelo
phase: 4
version: 0.1
depends_on:
  - docs/prd/001-prelo.md
  - docs/arch/001-prelo.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-24
title: Métricas, sugerencias y Prelo en la nube
---

# F4 — Métricas, sugerencias y Prelo en la nube

Hito M4 del PRD (FR-2, FR-15, NFR-7). Las reacciones y comentarios vuelven a Prelo cada día, `/prelo sugerir`
propone 3 temas con su origen, y Prelo corre en una EC2 creada con Terraform y desplegada desde GitHub Actions.

## F4.1 — Package: esqueleto

### F4.1.T1 — Tabla metricas, worker diario y /prelo sugerir con dobles

Añade `src/prelo/db/migracoes/002_metricas.sql` con la tabla `metricas` de *Data model* y los métodos del
`Repositorio` para guardarlas y leer la última de cada publicación. Crea `src/prelo/metricas.py` con un protocolo
`Leitor` (`canal`, `ler(publicacao) -> {"reacoes": int, "comentarios": list}`) y `coletar(leitores, repo)`, que
recorre las publicaciones de LinkedIn e Instagram y guarda una fila por publicación. En `slack.py`, `/prelo sugerir`
llama a una función `sugerir() -> list[{"tema", "origem", "link"}]` inyectada y muestra 3 temas con su link y un
botón `prelo_escolher` que inicia el post como `/prelo <tema>` con `origem = sugestao` (FR-2).

Done when: these tests pass in `tests/test_metricas_fluxo.py`, con dobles — `coletar` con dos publicaciones guarda
dos filas y una publicación sin lector de su canal se salta; la migración 002 se aplica sobre la 001 sin errores;
`/prelo sugerir` muestra 3 temas, cada uno con su link; pulsar `prelo_escolher` llama a `iniciar` con ese tema y
`origem = sugestao`; y `tests/test_slack.py` sigue pasando.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 3h
- **Reason**: Esqueleto sobre patrones ya fijados.
- **Dependencies**: F3.5.T1
- **Files**:
  - `src/prelo/db/migracoes/002_metricas.sql`
  - `src/prelo/db/repositorio.py`
  - `src/prelo/metricas.py`
  - `src/prelo/slack.py`
  - `tests/test_metricas_fluxo.py`
  - `tests/test_slack.py`

## F4.2 — Package: métricas

### F4.2.T1 — Lectores de LinkedIn e Instagram

Implementa en `src/prelo/metricas.py` los `Leitor` reales: LinkedIn (reacciones y comentarios del post por
`id_externo`; las impresiones no, ver *Non-goals* del PRD) e Instagram (`like_count`, `comments_count` y los
comentarios del media). Vía `httpx`, con los tokens de `config`. Un fallo de un lector no detiene la colecta de las
demás publicaciones y se avisa en Slack.

Done when: these tests pass in `tests/test_metricas.py`, con `respx` — LinkedIn devuelve el número de reacciones y
la lista de comentarios con autor y texto; Instagram igual; un 500 en una publicación no impide guardar las
demás; ningún error contiene un token.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 3h
- **Reason**: Dos clientes HTTP con paginación de comentarios.
- **Dependencies**: F4.1.T1
- **Files**:
  - `src/prelo/metricas.py`
  - `tests/test_metricas.py`

## F4.3 — Package: sugerencias

### F4.3.T1 — Sugerencia de temas

Implementa `src/prelo/sugestoes.py` con `sugerir() -> list[{"tema", "origem", "link"}]` según *sugestoes* de
docs/arch/001-prelo.md: junta los commits de los últimos 14 días de los repos de Héctor (GitHub API), la ruta de
estudio y noticias de IA (vía `Buscador`), y pide al `Modelo` 3 temas, cada uno con el link de su origen (commit,
documento o noticia). El contenido externo va delimitado como datos (NFR-4). Excluye temas ya publicados en los
últimos 30 días.

Done when: these tests pass in `tests/test_sugestoes.py`, con clientes falsos — devuelve exactamente 3 sugerencias,
cada una con `origem` y un `link` que existe en las entradas; un tema publicado hace 10 días no se sugiere; sin
commits recientes igual sugiere desde las otras fuentes; un mensaje de commit con instrucciones queda dentro del
delimitador.

- **Model**: agy/gemini-4-argon-medium
- **Estimate**: 3h
- **Reason**: Agregación de fuentes y prompt con validación.
- **Dependencies**: F4.1.T1
- **Files**:
  - `src/prelo/sugestoes.py`
  - `tests/test_sugestoes.py`

## F4.4 — Package: Terraform

### F4.4.T1 — Infra en AWS con Terraform

Crea `infra/terraform/` según D12: una EC2 (Ubuntu, Docker y Compose instalados por `user_data`) en una VPC con
subred pública, security group que solo abre 443 (para el webhook de GitHub y `POST /posts`) y SSH restringido a una
IP variable, Elastic IP, secretos en SSM Parameter Store (leídos al arrancar para generar el `.env`), un volumen EBS
para Postgres y backups diarios con snapshots de DLM. Estado remoto en S3. Variables y outputs documentados en
`infra/terraform/README.md`, incluida la medición de memoria de Langfuse v3 (riesgo del ARCH) y el plan B con
Langfuse Cloud.

Done when: `terraform fmt -check`, `terraform validate` y `tflint` pasan en `infra/terraform/`; el security group no
abre ningún puerto a `0.0.0.0/0` salvo 443; ningún secreto aparece en un `.tf`. No hay tests de Python.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 4h
- **Reason**: Terraform estándar con cuidado de seguridad de red y secretos.
- **Dependencies**: F4.1.T1
- **Files**:
  - `infra/terraform/`

## F4.5 — Package: deploy continuo y conexión

### F4.5.T1 — Deploy continuo y conexión final

Crea `.github/workflows/deploy.yml`: al hacer push a `main` con CI y evals verdes, construye la imagen, la publica
en GHCR y despliega en la EC2 por SSM Run Command (`docker compose pull && docker compose up -d`), sin claves SSH
en el repo (OIDC hacia un rol de AWS). En `app.py`, registra los lectores de métricas en un worker diario y pasa
`sugestoes.sugerir` a la app de Slack.

Done when: these tests pass in `tests/test_app.py` — la app registra el worker de métricas con período diario;
`/prelo sugerir` usa `sugestoes.sugerir`. Además `actionlint` pasa sobre `deploy.yml` y el workflow solo corre tras
CI y evals verdes.

- **Model**: claude/claude-sonnet-5-5
- **Estimate**: 3h
- **Reason**: Workflow de deploy con OIDC y cableado final.
- **Dependencies**: F4.2.T1, F4.3.T1, F4.4.T1
- **Files**:
  - `.github/workflows/deploy.yml`
  - `src/prelo/app.py`
  - `tests/test_app.py`
