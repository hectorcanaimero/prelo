from prelo.agentes.adaptador_linkedin import adaptador_linkedin
from prelo.config import Settings
from prelo.marca import carregar_regras, formato

REGLAS = {"max_palavras": 110, "max_emojis": 2, "hashtags": 3}


def test_post_que_cumple_no_tiene_violaciones():
    post = "Uma demo prova que o agente consegue. " * 5 + "E você? 🚀 https://x.com/a #ia #agentes #evals"
    assert formato(post, REGLAS) == []


def test_largo_con_emojis_y_hashtags_de_mas():
    post = "palavra " * 130 + "🔹 um 🔹 dois 🔹 três #a #b #c #d #e #f"
    detalles = [v["detalhe"] for v in formato(post, REGLAS)]
    assert detalles == ["máximo 110", "máximo 2 emojis", "exactamente 3 hashtags"]


def test_marca_toml_trae_las_reglas_de_linkedin_y_traca():
    regras = carregar_regras(Settings(_env_file=None))
    assert regras.linkedin == REGLAS
    assert "traça" in regras.frases


class Modelo:
    def __init__(self, salida):
        self.salida, self.prompts = salida, []

    def gerar(self, prompt, *, agente, post_id):
        self.prompts.append(prompt)
        return self.salida


def test_adaptador_pide_las_reglas_y_quita_el_markdown():
    m = Modelo("## Título\nUma **generation** por chamada, __sempre__.\n#ia #llm #langfuse")
    out = adaptador_linkedin(m, {"titulo": "T", "resumo": "R", "corpo": "C"}, None, post_id="p1", formato=REGLAS)
    assert "Máximo 110 palabras" in m.prompts[0] and "Exactamente 3 hashtags" in m.prompts[0]
    assert out["pt"]["corpo"] == "Título\nUma generation por chamada, sempre.\n#ia #llm #langfuse"
