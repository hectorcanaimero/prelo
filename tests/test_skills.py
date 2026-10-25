from prelo.agentes.adaptador_linkedin import adaptador_linkedin
from prelo.skills import SKILLS_DIR, skill


def test_skill_sin_cabecera_y_con_su_nombre():
    texto = skill("humanizer")
    assert texto.startswith('<skill nome="humanizer">') and texto.endswith("</skill>")
    assert "name: humanizer" not in texto and "Não é X, é Y" in texto


def test_las_tres_skills_existen():
    for n in ("voz-hector", "copywriting-linkedin", "humanizer"):
        assert (SKILLS_DIR / n / "SKILL.md").is_file()


def test_el_adaptador_lleva_voz_oficio_y_humanizer():
    class Modelo:
        prompt = ""

        def gerar(self, prompt, *, agente, post_id):
            Modelo.prompt = prompt
            return "ok"

    adaptador_linkedin(Modelo(), {"titulo": "T", "resumo": "R", "corpo": "C"}, None, post_id="p1")
    for n in ("voz-hector", "copywriting-linkedin", "humanizer"):
        assert f'<skill nome="{n}">' in Modelo.prompt
