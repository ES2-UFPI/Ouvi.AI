"""Testes do cache de áudio (US08): chave de cache e tabela AudioBlob.

Sem rede e sem créditos do TTS: o provedor é o falso e o armazenamento fica em memória. Os testes com duas
threads usam sessões próprias (o `db_session` não é visível de outra conexão) e apagam o que criaram.
"""
import threading
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.audio.cache import AudioBlobRepository, build_cache_key, normalize_ssml
from app.modules.audio.cache import key as key_module
from app.modules.audio.models import AudioBlob

SSML = '<speak version="1.0" xml:lang="pt-BR">Ela <lang xml:lang="en-US">gave up</lang> da corrida.</speak>'


# ---------- chave de cache ----------

def test_a_chave_e_deterministica_e_tem_64_caracteres_hexadecimais():
    chave = build_cache_key(SSML, "voz", "fake", "wav")
    assert chave == build_cache_key(SSML, "voz", "fake", "wav")
    assert len(chave) == 64 and int(chave, 16) >= 0


def test_o_formato_nao_diferencia_maiusculas():
    assert build_cache_key(SSML, "voz", "fake", "WAV") == build_cache_key(SSML, "voz", "fake", "wav")


def test_a_chave_e_igual_em_outro_processo():
    import subprocess
    import sys

    codigo = (
        "from app.modules.audio.cache import build_cache_key;"
        f"print(build_cache_key({SSML!r}, 'voz', 'fake', 'wav'))"
    )
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert saida.stdout.strip() == build_cache_key(SSML, "voz", "fake", "wav")


@pytest.mark.parametrize(
    "outra",
    [
        (SSML.replace("gave up", "set off"), "voz", "fake", "wav"),  # outro texto
        (SSML.replace('xml:lang="en-US"', 'xml:lang="en-GB"'), "voz", "fake", "wav"),  # outro idioma
        (SSML, "outra-voz", "fake", "wav"),
        (SSML, "voz", "azure", "wav"),
        (SSML, "voz", "fake", "mp3"),
    ],
)
def test_mudar_qualquer_campo_muda_a_chave(outra):
    assert build_cache_key(*outra) != build_cache_key(SSML, "voz", "fake", "wav")


def test_mudar_a_versao_muda_a_chave(monkeypatch):
    antes = build_cache_key(SSML, "voz", "fake", "wav")
    monkeypatch.setattr(key_module, "CACHE_KEY_VERSION", key_module.CACHE_KEY_VERSION + 1)
    assert build_cache_key(SSML, "voz", "fake", "wav") != antes


def test_espacos_fora_das_tags_nao_mudam_a_chave():
    espacado = (
        '  <speak version="1.0" xml:lang="pt-BR">\n   Ela   <lang xml:lang="en-US">gave   up</lang>\t'
        "da corrida.\n</speak>\n"
    )
    assert normalize_ssml(espacado) == SSML
    assert build_cache_key(espacado, "voz", "fake", "wav") == build_cache_key(SSML, "voz", "fake", "wav")


def test_espaco_entre_palavras_ainda_conta():
    # Tirar um espaço que separa palavras muda o que é falado: a chave tem que mudar
    colado = SSML.replace("</lang> da", "</lang>da")
    assert build_cache_key(colado, "voz", "fake", "wav") != build_cache_key(SSML, "voz", "fake", "wav")


# ---------- AudioBlobRepository ----------

def _dados(chave: str, **extra) -> dict:
    dados = dict(
        cache_key=chave, storage_key=f"cache/{chave}.wav", audio_format="wav",
        duration_ms=1200, size_bytes=4000, char_count=50,
    )
    dados.update(extra)
    return dados


def test_create_if_absent_duas_vezes_devolve_o_mesmo_registro(db_session):
    repo = AudioBlobRepository(db_session)
    chave = uuid.uuid4().hex * 2
    primeiro = repo.create_if_absent(**_dados(chave))
    segundo = repo.create_if_absent(**_dados(chave, storage_key="outra/chave.wav", size_bytes=1))
    assert primeiro.id == segundo.id
    assert segundo.storage_key == f"cache/{chave}.wav"  # o existente não é alterado
    assert (segundo.hit_count, segundo.miss_count) == (0, 1)
    assert repo.get_by_key(chave).id == primeiro.id


def test_create_if_absent_simultaneo_cria_um_unico_registro(db_session):  # db_session: pula sem banco
    from app.core.database import engine

    chave = uuid.uuid4().hex * 2
    barreira = threading.Barrier(2)
    ids: list[int] = []
    erros: list[BaseException] = []

    def criar():
        try:
            with Session(engine) as db:
                barreira.wait(timeout=10)
                ids.append(AudioBlobRepository(db).create_if_absent(**_dados(chave)).id)
                db.commit()
        except BaseException as exc:  # noqa: BLE001 - o erro da thread precisa chegar ao teste
            erros.append(exc)

    try:
        threads = [threading.Thread(target=criar) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert erros == []
        assert len(ids) == 2 and ids[0] == ids[1]
    finally:
        with Session(engine) as db:
            db.execute(delete(AudioBlob).where(AudioBlob.cache_key == chave))
            db.commit()
