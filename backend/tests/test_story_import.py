"""US18: o usuário envia o próprio texto (POST /stories/import) e ouve com os mesmos filtros."""
import json

import pytest

from app.modules.stories.importer import (
    BilingualTextExtractor,
    ExtractorFactory,
    SeedJsonExtractor,
    StoryImportError,
)

TXT = """# A Raposa e a Gralha

The Fox quickly picked it up, and thus addressed the Crow.
A Raposa rapidamente a apanhou e assim falou à Gralha.

"My good Crow, your voice is right enough, but your wit is wanting."
"Minha boa Gralha, a sua voz é boa o bastante, mas falta-lhe juízo."

= Glossário: termo e como aparece no português
= picked it up -> apanhou
= wit -> juízo
""".encode()


def _upload(api, headers, name="historia.txt", data=TXT, **form):
    return api.post("/stories/import", headers=headers, files={"file": (name, data, "text/plain")}, data=form)


# ---------- extratores (Strategy) e fábrica ----------


def test_txt_le_titulo_pares_e_glossario():
    story = BilingualTextExtractor().extract(TXT)
    assert story.title == "A Raposa e a Gralha"
    assert len(story.segments) == 2
    assert story.segments[0][1].startswith("A Raposa rapidamente")
    assert story.glossary == {"picked it up": ["apanhou"], "wit": ["juízo"]}


def test_txt_com_frase_sem_traducao_e_recusado():
    with pytest.raises(StoryImportError, match="sem par"):
        BilingualTextExtractor().extract(b"One sentence only.")


def test_json_no_formato_do_seed_usa_os_phrasal_verbs_como_glossario():
    raw = {
        "title": "T",
        "segments": [
            {"en": "She set out early.", "pt": "Ela partiu cedo.", "phrasal_verbs": [{"lemma": "set out", "en": "set out", "pt": "partiu"}]}
        ],
        "glossary": {"early": "cedo"},
    }
    story = SeedJsonExtractor().extract(json.dumps(raw).encode())
    assert story.segments == [("She set out early.", "Ela partiu cedo.")]
    assert story.glossary == {"set out": ["partiu"], "early": ["cedo"]}


def test_json_invalido_e_recusado():
    with pytest.raises(StoryImportError, match="JSON inválido"):
        SeedJsonExtractor().extract(b"{nao e json")


def test_fabrica_escolhe_pela_extensao_e_recusa_outras():
    assert isinstance(ExtractorFactory.for_filename("a.TXT"), BilingualTextExtractor)
    assert isinstance(ExtractorFactory.for_filename("a.json"), SeedJsonExtractor)
    with pytest.raises(StoryImportError, match="não suportado"):
        ExtractorFactory.for_filename("a.pdf")


# ---------- rota ----------


def test_enviar_exige_token(api):
    assert _upload(api, {}).status_code == 401


def test_enviar_cria_anota_e_alinha_pelo_glossario(api, make_user):
    _, headers = make_user()
    resposta = _upload(api, headers)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["story"]["title"] == "A Raposa e a Gralha"
    assert corpo["story"]["segment_count"] == 2
    assert corpo["story"]["is_mine"] is True
    assert corpo["annotations"] >= 2 and corpo["aligned"] == corpo["annotations"]

    segmentos = api.get(f"/stories/{corpo['story']['id']}/segments", headers=headers).json()["segments"]
    pares = {a["en_text"]: a["pt_text"] for s in segmentos for a in s["annotations"]}
    assert pares["picked it up"] == "apanhou"
    assert pares["wit"] == "juízo"


def test_titulo_do_formulario_vence_o_do_arquivo(api, make_user):
    _, headers = make_user()
    assert _upload(api, headers, title="Meu título").json()["story"]["title"] == "Meu título"


def test_historia_enviada_e_particular(api, make_user):
    _, dono = make_user()
    _, outro = make_user()
    story_id = _upload(api, dono).json()["story"]["id"]

    assert any(s["id"] == story_id and s["is_mine"] for s in api.get("/stories", headers=dono).json())
    assert all(s["id"] != story_id for s in api.get("/stories", headers=outro).json())
    assert api.get(f"/stories/{story_id}/segments", headers=outro).status_code == 404


@pytest.mark.parametrize(
    ("name", "data", "mensagem"),
    [
        ("vazio.txt", b"", "vazio"),
        ("a.pdf", b"%PDF", "não suportado"),
        ("grande.txt", b"x" * 100_001, "grande demais"),
        ("impar.txt", b"Only English.", "sem par"),
    ],
    ids=["vazio", "pdf", "grande", "sem-traducao"],
)
def test_arquivos_invalidos_sao_recusados_com_mensagem(api, make_user, name, data, mensagem):
    _, headers = make_user()
    resposta = _upload(api, headers, name=name, data=data)
    assert resposta.status_code == 422
    assert mensagem in resposta.json()["detail"]
