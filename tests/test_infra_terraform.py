"""Criterios estáticos de infra/terraform (terraform/tflint no corren en el CI de Python)."""

import re
from pathlib import Path

TF_DIR = Path(__file__).resolve().parent.parent / "infra" / "terraform"
TF_FILES = sorted(TF_DIR.glob("*.tf"))
REGLAS = ("aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule")


def _blocks(texto: str, tipo: str) -> list[str]:
    """Cuerpos de `resource "<tipo>" "x" { ... }` (llave de cierre en columna 0)."""
    patron = r'^resource "' + tipo + r'" "[^"]+" \{\n(.*?)^\}'
    return re.findall(patron, texto, re.DOTALL | re.MULTILINE)


def test_sg_solo_abre_443_a_internet():
    abiertos = []
    for f in TF_FILES:
        for tipo in REGLAS:
            for b in _blocks(f.read_text(), tipo):
                if "0.0.0.0/0" in b:
                    abiertos.append(re.search(r"from_port\s*=\s*(\d+)", b).group(1))
    assert abiertos and set(abiertos) == {"443"}


def test_sg_sin_reglas_inline():
    for f in TF_FILES:
        for b in _blocks(f.read_text(), "aws_security_group"):
            assert "0.0.0.0/0" not in b
            assert "ingress" not in b


def test_ssh_restringido_a_variable():
    main = (TF_DIR / "main.tf").read_text()
    ssh = [b for b in _blocks(main, REGLAS[0]) if re.search(r"from_port\s*=\s*22\b", b)]
    assert len(ssh) == 1 and "var.ssh_cidr" in ssh[0]


def test_ningun_secreto_en_tf():
    patrones = [
        r"AKIA[0-9A-Z]{16}",
        r"sk-[A-Za-z0-9]{20,}",
        r"xox[bap]-",
        r"ghp_[A-Za-z0-9]{20,}",
        r"BEGIN [A-Z ]*PRIVATE KEY",
    ]
    for f in TF_FILES:
        for p in patrones:
            assert not re.search(p, f.read_text()), f"{f.name}: {p}"
