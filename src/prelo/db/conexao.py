import psycopg

# Postgres suele estar en otra máquina: un NAT o firewall corta en silencio una conexión que pasa minutos sin tráfico,
# y psycopg se queda esperando para siempre. Con keepalive TCP la conexión no queda ociosa y, si igual se cae, da error
# en ~1 min en vez de colgar el post.
KEEPALIVE = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5}


def conectar(url: str, **kwargs: object) -> psycopg.Connection:
    """Conexion en autocommit: cada metodo del repositorio es una sentencia atomica."""
    return psycopg.connect(url, autocommit=True, **KEEPALIVE, **kwargs)  # type: ignore[arg-type]
