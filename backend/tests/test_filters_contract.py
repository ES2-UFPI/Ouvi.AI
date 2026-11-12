"""Testes do contrato do filtro (#101): tabela de combinações, nível das palavras e GET /filters/options."""
import pytest
from pydantic import ValidationError

from app.modules.audio.repository import compute_rules_hash
from app.modules.filters.models import ListeningFilter
from app.modules.filters.schemas import SCENARIOS, FilterRules, StoredFilterRules

CENARIO_A = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "medium"}
CENARIO_B = {
    "base_language": "en",
    "segment_types": ["difficult_words"],
    "word_level": "advanced",
    "density": "low",
}


def corpo(**regras):
    return {"story_id": None, "rules": regras}


# ---------- combinações válidas: todas as da tabela ----------

@pytest.mark.parametrize("cenario", SCENARIOS, ids=lambda s: s.base_language)
def test_toda_combinacao_da_tabela_e_aceita(cenario):
    niveis = cenario.word_levels or [None]
    for tipo in cenario.segment_types:
        for nivel in niveis:
            regras = {"base_language": cenario.base_language, "segment_types": [tipo], "density": "high"}
            if nivel:
                regras["word_level"] = nivel
            assert FilterRules.model_validate(regras).model_dump() == regras


@pytest.mark.parametrize("nivel", ["intermediate", "advanced"])
def test_cenario_b_com_nivel_e_aceito_pela_api(api, make_user, nivel):
    _, headers = make_user()
    regras = {**CENARIO_B, "word_level": nivel}
    resposta = api.post("/filters", json=corpo(**regras), headers=headers)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["rules"] == regras


def test_cenario_a_continua_aceito_e_sem_word_level(api, make_user):
    _, headers = make_user()
    resposta = api.post("/filters", json=corpo(**CENARIO_A), headers=headers)
    assert resposta.status_code == 201
    # a chave word_level nem aparece: as regras ficam iguais às de antes do campo existir
    assert resposta.json()["rules"] == CENARIO_A


def test_hash_do_cenario_a_nao_muda_com_o_novo_campo():
    # o cache de áudio (US08) usa o hash das regras: o Cenário A não pode perder o áudio já gerado
    assert compute_rules_hash(FilterRules.model_validate(CENARIO_A).model_dump()) == compute_rules_hash(CENARIO_A)


# ---------- combinações inválidas: 422 com mensagem clara ----------

@pytest.mark.parametrize(
    "regras, trecho_da_mensagem",
    [
        ({**CENARIO_A, "base_language": "en"}, "combinação não disponível"),  # en + phrasal_verbs
        ({**CENARIO_B, "base_language": "pt"}, "combinação não disponível"),  # pt + difficult_words
        ({**CENARIO_A, "segment_types": ["phrasal_verbs", "difficult_words"]}, "combinação não disponível"),
        ({**CENARIO_A, "segment_types": ["advanced_vocabulary"]}, "combinação não disponível"),  # US11, ainda não
        ({**CENARIO_B, "segment_types": ["advanced_vocabulary"]}, "combinação não disponível"),
        ({k: v for k, v in CENARIO_B.items() if k != "word_level"}, "word_level é obrigatório"),
        ({**CENARIO_A, "word_level": "advanced"}, "word_level não se aplica"),
        ({**CENARIO_B, "word_level": "beginner"}, "word_level"),
    ],
)
def test_combinacoes_fora_da_tabela_respondem_422(api, make_user, regras, trecho_da_mensagem):
    _, headers = make_user()
    resposta = api.post("/filters", json=corpo(**regras), headers=headers)
    assert resposta.status_code == 422
    assert trecho_da_mensagem in resposta.text


def test_put_com_combinacao_invalida_responde_422(api, make_user):
    _, headers = make_user()
    criado = api.post("/filters", json=corpo(**CENARIO_A), headers=headers).json()
    resposta = api.put(f"/filters/{criado['id']}", json=corpo(**{**CENARIO_A, "base_language": "en"}), headers=headers)
    assert resposta.status_code == 422


def test_validacao_direta_explica_o_erro():
    with pytest.raises(ValidationError, match="os tipos aceitos são: phrasal_verbs"):
        FilterRules.model_validate({**CENARIO_A, "base_language": "pt", "segment_types": ["difficult_words"]})


# ---------- filtros já salvos continuam sendo lidos ----------

def test_filtro_antigo_fora_da_tabela_continua_sendo_lido(api, make_user, db_session):
    usuario, headers = make_user()
    # gravado direto no banco, como um filtro salvo antes desta validação existir
    antigo = ListeningFilter(
        user_id=usuario["id"], story_id=None,
        rules={"base_language": "en", "segment_types": ["phrasal_verbs"], "density": "high"},
    )
    db_session.add(antigo)
    db_session.commit()

    assert api.get(f"/filters/{antigo.id}", headers=headers).status_code == 200
    assert api.get("/filters", headers=headers).status_code == 200
    # a leitura é tolerante, mas a gravação continua exigindo uma combinação válida
    StoredFilterRules.model_validate(antigo.rules)


# ---------- GET /filters/options ----------

def test_options_devolve_a_tabela_de_cenarios(api, make_user):
    _, headers = make_user()
    resposta = api.get("/filters/options", headers=headers)
    assert resposta.status_code == 200
    opcoes = resposta.json()
    cenarios = {c["base_language"]: c for c in opcoes["scenarios"]}
    assert cenarios["pt"]["segment_types"] == ["phrasal_verbs"] and cenarios["pt"]["word_levels"] == []
    assert cenarios["en"]["segment_types"] == ["difficult_words"]
    assert cenarios["en"]["word_levels"] == ["intermediate", "advanced"]
    assert opcoes["densities"] == ["low", "medium", "high"]
    assert opcoes["word_levels"] == ["intermediate", "advanced"]


def test_options_exige_token(api):
    assert api.get("/filters/options").status_code == 401


def test_options_aparece_no_openapi(api):
    assert "/filters/options" in api.get("/openapi.json").json()["paths"]
