import psycopg


def conectar(url: str) -> psycopg.Connection:
    """Conexion en autocommit: cada metodo del repositorio es una sentencia atomica."""
    return psycopg.connect(url, autocommit=True)
