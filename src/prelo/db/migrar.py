from pathlib import Path

import psycopg

DIR = Path(__file__).parent / "migracoes"


def aplicar_migracoes(conn: psycopg.Connection) -> None:
    """Aplica las migraciones `NNN_*.sql` pendientes, en orden; las aplicadas quedan en `migracoes`."""
    conn.execute("CREATE TABLE IF NOT EXISTS migracoes (nome text PRIMARY KEY, aplicada_em timestamptz DEFAULT now())")
    feitas = {r[0] for r in conn.execute("SELECT nome FROM migracoes")}
    for arquivo in sorted(DIR.glob("[0-9][0-9][0-9]_*.sql")):
        if arquivo.name in feitas:
            continue
        with conn.transaction():
            conn.execute(arquivo.read_text())
            conn.execute("INSERT INTO migracoes (nome) VALUES (%s)", (arquivo.name,))
