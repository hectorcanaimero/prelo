# Infra de Prelo en AWS (D12)

Una EC2 Ubuntu 24.04 con el mismo `docker-compose.yml` del repo, en una VPC con subred pública.

| Recurso | Detalle |
| --- | --- |
| Red | VPC, subred pública, internet gateway, Elastic IP |
| Security group | Entrada: **443** desde `0.0.0.0/0` (webhook de GitHub y `POST /posts`) y **22** solo desde `ssh_cidr`. Ningún otro puerto. |
| Cómputo | EC2 con Docker y Compose instalados por `user_data`; IMDSv2 obligatorio; disco raíz cifrado |
| Secretos | SSM Parameter Store bajo `ssm_prefix`; `user_data` los lee al arrancar y escribe `/opt/prelo/.env` (modo 600) |
| Datos | Volumen EBS cifrado montado en `/data/postgres`; `docker-compose.override.yml` lo usa para Postgres |
| Backups | DLM: snapshot diario (05:00 UTC) de los volúmenes con tag `Backup=prelo-daily`, `snapshot_retention` copias |
| Estado | Backend S3 (`versions.tf`), sin nombres de bucket en el repo |

## Uso

```bash
cd infra/terraform
terraform init \
  -backend-config="bucket=<bucket-de-estado>" \
  -backend-config="region=<region>"
terraform apply -var ssh_cidr=203.0.113.7/32 -var key_name=<key-pair>
```

El bucket de estado se crea a mano antes (con versionado activado). Los secretos **no** se declaran en Terraform:
créalos como `SecureString` antes del primer arranque, un parámetro por variable del `.env`:

```bash
aws ssm put-parameter --type SecureString --name /prelo/ANTHROPIC_API_KEY --value '<valor>'
```

Variables esperadas (ver `.env.example`): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY`, `SLACK_*`,
`LINKEDIN_*`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `IG_*`, `R2_*`, `LANGFUSE_*`, `PRELO_API_TOKEN`,
`POSTGRES_PASSWORD`, `NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY`, `CLICKHOUSE_PASSWORD`,
`REDIS_AUTH`, `MINIO_ROOT_PASSWORD`. Para cambiar un secreto: actualiza el parámetro y reejecuta la generación del
`.env` (reinicia la instancia o ejecuta el bloque de `user_data` por SSM Run Command).

## Variables

| Variable | Default | Descripción |
| --- | --- | --- |
| `region` | `us-east-1` | Región de AWS |
| `instance_type` | `t3.large` | Tipo de EC2 (8 GiB; ver medición de Langfuse) |
| `ssh_cidr` | — (obligatoria) | CIDR con acceso SSH; se rechaza `0.0.0.0/0` |
| `key_name` | — (obligatoria) | Key pair EC2 existente |
| `vpc_cidr` | `10.20.0.0/16` | CIDR de la VPC |
| `public_subnet_cidr` | `10.20.1.0/24` | CIDR de la subred pública |
| `data_volume_size` | `20` | GiB del volumen de Postgres |
| `snapshot_retention` | `14` | Snapshots diarios conservados |
| `ssm_prefix` | `/prelo` | Prefijo de los secretos en SSM |

## Outputs

| Output | Uso |
| --- | --- |
| `public_ip` | Elastic IP: DNS y URL del webhook de GitHub |
| `instance_id` | Destino de SSM Run Command (deploy, F4.5) |
| `data_volume_id` | Volumen de Postgres |
| `ssm_prefix` | Dónde deben existir los secretos |

## Pendiente fuera de esta tarea

- El security group solo deja entrar 443: necesita un proxy TLS (p. ej. Caddy) delante de `prelo:8000`. El compose
  actual publica 8000, 3000 y 5432 en el host; el security group los bloquea desde fuera, pero el proxy y el
  certificado se añaden en el despliegue (F4.5).
- El código de la app llega por `docker compose pull && up -d` (F4.5); `user_data` solo prepara el host.

## Memoria de Langfuse v3 (riesgo del ARCH)

Langfuse v3 arranca seis contenedores además de `prelo`: `langfuse`, `langfuse-worker`, `clickhouse`, `redis`,
`minio` y Postgres. Estimación de partida, **por confirmar con la medición** (no se pudo medir en esta tarea:
requiere una instancia desplegada):

| Servicio | RAM aprox. |
| --- | --- |
| clickhouse | 1–2 GiB |
| langfuse (web) | ~1 GiB |
| langfuse-worker | ~0.5–1 GiB |
| postgres | ~0.3 GiB |
| redis + minio | ~0.3 GiB |
| prelo | ~0.5 GiB |

Total ≈ 4–5 GiB en reposo, de ahí el `t3.large` (8 GiB). Un `t3.small` (2 GiB) o `t3.medium` (4 GiB) no caben.

Cómo medirlo tras `terraform apply` y `docker compose up -d`:

```bash
ssh ubuntu@<public_ip>
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}'
free -m
```

Déjalo corriendo un par de ejecuciones del grafo y anota el pico. Regla: si `free -m` muestra menos de 1 GiB
disponible en el pico, sube un tamaño de instancia o aplica el plan B.

## Plan B: Langfuse Cloud

Si no cabe o el costo no compensa:

1. Crea un proyecto en Langfuse Cloud (plan gratis) y copia las claves.
2. En SSM pon `LANGFUSE_HOST` (p. ej. `https://cloud.langfuse.com`), `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY`.
3. Arranca solo `prelo` y Postgres: `docker compose up -d postgres prelo`. Sin `depends_on` de `langfuse`
   (usa `--no-deps` o un override), así `clickhouse`, `redis`, `minio` y `langfuse*` no corren y bajan a
   `t3.small`/`t3.medium` con `instance_type`.

El código no cambia: el cliente lee las mismas variables `LANGFUSE_*`.
