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

@pytest.mark.parametrize("cenario", SCENARIOS, ids=lambda s: s.segment_types[0])
def test_toda_combinacao_da_tabela_e_aceita(cenario):
    niveis = cenario.word_levels or [None]
    for tipo in cenario.segment_types:
        for nivel in niveis:
            regras = {"base_language": cenario.base_language, "segment_types": [tipo], "density": "high"}
            if nivel:
                regras["word_level"] = nivel
            for progressao in cenario.progressions:
                if progressao != "fixed":  # a fixa é a padrão e não aparece nas regras
                    regras["progression"] = progressao
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
    cenarios = {(c["base_language"], tuple(c["segment_types"])): c for c in opcoes["scenarios"]}
    assert cenarios[("pt", ("phrasal_verbs",))]["word_levels"] == []
    assert cenarios[("pt", ("advanced_vocabulary",))]["word_levels"] == []  # Cenário C (US11)
    cenarios = {c["base_language"]: c for c in opcoes["scenarios"]}
    assert cenarios["en"]["segment_types"] == ["difficult_words"]
    assert cenarios["en"]["word_levels"] == ["intermediate", "advanced"]
    assert opcoes["densities"] == ["low", "medium", "high"]
    assert opcoes["word_levels"] == ["intermediate", "advanced"]


def test_options_exige_token(api):
    assert api.get("/filters/options").status_code == 401


def test_options_aparece_no_openapi(api):
    assert "/filters/options" in api.get("/openapi.json").json()["paths"]


# ---------- Cenário C (US11): vocabulário avançado com base português e densidade crescente ----------

CENARIO_C = {
    "base_language": "pt",
    "segment_types": ["advanced_vocabulary"],
    "density": "medium",
    "progression": "increasing",
}


def test_cenario_c_e_aceito_pela_api_e_reaparece_igual(api, make_user):
    _, headers = make_user()
    criado = api.post("/filters", json=corpo(**CENARIO_C), headers=headers)
    assert criado.status_code == 201, criado.text
    assert criado.json()["rules"] == CENARIO_C
    assert api.get(f"/filters/{criado.json()['id']}", headers=headers).json()["rules"] == CENARIO_C


@pytest.mark.parametrize(
    "regras, trecho_da_mensagem",
    [
        # o Cenário C EXIGE a progressão crescente
        ({k: v for k, v in CENARIO_C.items() if k != "progression"}, "progression é obrigatória com advanced_vocabulary: use 'increasing'"),
        ({**CENARIO_C, "progression": "fixed"}, "progression 'fixed' não se aplica a advanced_vocabulary: use 'increasing'"),
        # e os Cenários A e B continuam com densidade fixa
        ({**CENARIO_A, "progression": "increasing"}, "progression 'increasing' não se aplica a phrasal_verbs: use 'fixed'"),
        ({**CENARIO_B, "progression": "increasing"}, "progression 'increasing' não se aplica a difficult_words"),
        ({**CENARIO_C, "progression": "decreasing"}, "progression"),
        ({**CENARIO_C, "word_level": "advanced"}, "word_level não se aplica"),
        ({**CENARIO_C, "segment_types": ["advanced_vocabulary", "difficult_words"]}, "combinação não disponível"),
        # A e C têm a mesma base, mas são cenários diferentes: não se misturam no mesmo filtro
        ({**CENARIO_C, "segment_types": ["phrasal_verbs", "advanced_vocabulary"]}, "cenários diferentes"),
    ],
)
def test_progressao_e_combinacoes_do_cenario_c_respondem_422(api, make_user, regras, trecho_da_mensagem):
    _, headers = make_user()
    resposta = api.post("/filters", json=corpo(**regras), headers=headers)
    assert resposta.status_code == 422
    assert trecho_da_mensagem in resposta.text


@pytest.mark.parametrize("cenario", [CENARIO_A, CENARIO_B])
def test_filtros_antigos_sem_progressao_continuam_validos_e_com_o_mesmo_hash(cenario):
    # a fixa é a padrão: explícita ou ausente, as regras (e o hash do cache de áudio) são as de antes do campo
    explicita = FilterRules.model_validate({**cenario, "progression": "fixed"}).model_dump()
    assert explicita == FilterRules.model_validate(cenario).model_dump() == cenario
    assert compute_rules_hash(explicita) == compute_rules_hash(cenario)


def test_mudar_a_progressao_ou_a_densidade_muda_o_hash():
    hashes = {
        compute_rules_hash(FilterRules.model_validate(regras).model_dump())
        for regras in (
            CENARIO_C,
            {**CENARIO_C, "density": "high"},
            {**CENARIO_C, "segment_types": ["phrasal_verbs"], "progression": "fixed"},
        )
    }
    assert len(hashes) == 3


def test_options_lista_as_progressoes_e_a_de_cada_cenario(api, make_user):
    _, headers = make_user()
    opcoes = api.get("/filters/options", headers=headers).json()
    assert opcoes["progressions"] == ["fixed", "increasing"]
    por_tipo = {c["segment_types"][0]: c["progressions"] for c in opcoes["scenarios"]}
    assert por_tipo == {"phrasal_verbs": ["fixed"], "difficult_words": ["fixed"], "advanced_vocabulary": ["increasing"]}


def test_mensagem_lista_os_tipos_dos_dois_cenarios_em_portugues():
    with pytest.raises(ValidationError, match="os tipos aceitos são: phrasal_verbs, advanced_vocabulary"):
        FilterRules.model_validate({**CENARIO_C, "segment_types": ["difficult_words"]})
