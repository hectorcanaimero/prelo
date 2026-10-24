import os
import uuid

import psycopg
import pytest
from psycopg import sql

from prelo.db.migrar import aplicar_migracoes


@pytest.fixture
def pg_url():
    """URL de un schema limpio por test, con las migraciones aplicadas."""
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("TEST_DATABASE_URL no definida")
    schema = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        sep = "&" if "?" in base else "?"
        url = f"{base}{sep}options=-csearch_path%3D{schema}"
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                aplicar_migracoes(conn)
            yield url
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
