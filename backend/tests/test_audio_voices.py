"""Testes da voz escolhida pelo idioma base do filtro (#106).

Cenário A (base português) e cenário B (base inglês) podem usar vozes diferentes, definidas só por variáveis de
ambiente. Sem `TTS_VOICE_ID_PT`/`TTS_VOICE_ID_EN`, vale a `TTS_VOICE_ID`. Tudo com o provedor falso: sem rede e sem chave.
"""
import pytest
from sqlalchemy import select

from app.core.config import FAKE_VOICE_ID, Settings
from app.integrations.tts import create_tts_provider
from app.modules.audio import generation_router
from app.modules.audio.models import AudioAsset
from app.modules.stories.models import KIND_DIFFICULT_WORD, Annotation
from tests.test_audio_facade import nova_historia
from tests.test_audio_generation_api import (  # noqa: F401
    ana,
    audio_da_frase,
    criar_filtro,
    gerar,
    sessoes,
    status_de,
    storage,
    tts,
)

REGRAS_PT = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "high"}
REGRAS_EN = {"base_language": "en", "segment_types": ["difficult_words"], "word_level": "intermediate", "density": "high"}

# Uma palavra difícil por frase (alinhada ao português), para o filtro com idioma base inglês
PALAVRAS = [("race", "corrida"), ("light", "luz"), ("early", "cedo")]


# ---------- as Settings ----------

def test_sem_voz_por_idioma_as_duas_usam_a_voz_padrao():
    settings = Settings(tts_voice_id="padrao")
    assert settings.voice_for("pt") == settings.voice_for("en") == "padrao"


def test_a_voz_do_idioma_vence_a_padrao_e_o_outro_idioma_continua_na_padrao():
    settings = Settings(tts_voice_id="padrao", tts_voice_id_en="voz-en")
    assert settings.voice_for("en") == "voz-en"
    assert settings.voice_for("pt") == "padrao"


def test_idioma_desconhecido_usa_a_voz_padrao():
    assert Settings(tts_voice_id="padrao", tts_voice_id_pt="voz-pt").voice_for("es") == "padrao"


# ---------- a fábrica do Azure ----------

def azure(**kwargs) -> Settings:
    valores = {"tts_provider": "azure", "tts_api_key": "chave-de-teste", "tts_region": "brazilsouth"}
    return Settings(**{**valores, **kwargs})


def test_azure_aceita_as_duas_vozes_por_idioma_sem_a_voz_padrao():
    provedor = create_tts_provider(azure(tts_voice_id_pt="pt-BR-ThalitaMultilingualNeural", tts_voice_id_en="en-US-AvaMultilingualNeural"))
    assert provedor.provider_name == "azure"


def test_azure_recusa_quando_um_idioma_ficaria_com_a_voz_do_provedor_falso():
    with pytest.raises(ValueError, match="TTS_VOICE_ID_PT e TTS_VOICE_ID_EN"):
        create_tts_provider(azure(tts_voice_id=FAKE_VOICE_ID, tts_voice_id_pt="pt-BR-ThalitaMultilingualNeural"))


def test_azure_so_com_a_voz_padrao_continua_funcionando():
    assert create_tts_provider(azure(tts_voice_id="pt-BR-ThalitaMultilingualNeural")).provider_name == "azure"


# ---------- a geração pela API ----------

@pytest.fixture
def historia(db_session):
    """A história de sempre (phrasal verbs, Cenário A), com uma palavra difícil por frase (Cenário B)."""
    story = nova_historia()
    for segmento, (en, pt) in zip(story.segments, PALAVRAS):
        es, ps = segmento.text_en.index(en), segmento.text_pt.index(pt)
        segmento.annotations.append(
            Annotation(
                kind=KIND_DIFFICULT_WORD, lemma=en, en_start=es, en_end=es + len(en), en_text=en,
                pt_start=ps, pt_end=ps + len(pt), pt_text=pt, extra={"level": "advanced"},
            )
        )
    db_session.add(story)
    db_session.commit()
    return story


@pytest.fixture
def vozes(monkeypatch):
    """Troca as Settings da rota de geração por outras com as vozes pedidas."""

    def _definir(**kwargs):
        settings = Settings(**kwargs)
        monkeypatch.setattr(generation_router, "get_settings", lambda: settings)
        return settings

    return _definir


def vozes_dos_assets(db_session, story_id: int) -> set[str]:
    db_session.expire_all()
    return set(db_session.scalars(select(AudioAsset.voice_id).where(AudioAsset.story_id == story_id)))


def test_filtro_em_portugues_usa_a_voz_pt_e_em_ingles_usa_a_voz_en(api, ana, historia, tts, vozes, db_session):
    vozes(tts_voice_id="padrao", tts_voice_id_pt="voz-pt", tts_voice_id_en="voz-en")
    filtro_pt = criar_filtro(api, ana, historia.id, REGRAS_PT)
    filtro_en = criar_filtro(api, ana, historia.id, REGRAS_EN)

    gerar(api, ana, historia.id, filtro_pt)
    assert {c.voice_id for c in tts.calls} == {"voz-pt"}
    gerar(api, ana, historia.id, filtro_en)

    assert {c.voice_id for c in tts.calls[3:]} == {"voz-en"}
    assert vozes_dos_assets(db_session, historia.id) == {"voz-pt", "voz-en"}  # a voz fica no AudioAsset


def test_o_status_e_o_audio_da_frase_acompanham_a_voz_do_idioma(api, ana, historia, vozes):
    vozes(tts_voice_id="padrao", tts_voice_id_pt="voz-pt", tts_voice_id_en="voz-en")
    filtro_pt = criar_filtro(api, ana, historia.id, REGRAS_PT)
    filtro_en = criar_filtro(api, ana, historia.id, REGRAS_EN)
    gerar(api, ana, historia.id, filtro_pt)

    # Só o filtro em português foi gerado: o em inglês (outra voz, outras regras) continua pendente
    assert status_de(api, ana, historia.id, filtro_pt).json()["state"] == "ready"
    assert status_de(api, ana, historia.id, filtro_en).json()["state"] == "pending"
    assert audio_da_frase(api, ana, historia.segments[0].id, filtro_pt).status_code == 200
    assert audio_da_frase(api, ana, historia.segments[0].id, filtro_en).status_code == 409


def test_sem_voz_por_idioma_os_dois_filtros_usam_a_voz_padrao(api, ana, historia, tts, vozes, db_session):
    vozes(tts_voice_id="padrao")
    gerar(api, ana, historia.id, criar_filtro(api, ana, historia.id, REGRAS_PT))
    gerar(api, ana, historia.id, criar_filtro(api, ana, historia.id, REGRAS_EN))

    assert {c.voice_id for c in tts.calls} == {"padrao"}
    assert vozes_dos_assets(db_session, historia.id) == {"padrao"}


def test_trocar_a_voz_gera_audio_novo_porque_ela_entra_na_chave_do_cache(api, ana, historia, tts, vozes):
    filtro = criar_filtro(api, ana, historia.id, REGRAS_PT)
    vozes(tts_voice_id="voz-a")
    gerar(api, ana, historia.id, filtro)
    assert len(tts.calls) == 3

    vozes(tts_voice_id="voz-a", tts_voice_id_pt="voz-b")
    gerar(api, ana, historia.id, filtro)

    assert len(tts.calls) == 6
    assert {c.voice_id for c in tts.calls[3:]} == {"voz-b"}
