"""Testes da geração com cache de áudio (US08): acerto, erro, outro filtro, outro usuário, arquivo sumido e
simultaneidade.

Tudo com o FakeTTSProvider (as chamadas ficam em `calls`) e o InMemoryStorage: sem rede e sem créditos do TTS.
Os testes de simultaneidade usam sessões próprias (o `db_session` não é visível de outra conexão) e apagam o
que criaram no fim.
"""
import threading
import time
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.storage import InMemoryStorage, StorageError
from app.integrations.tts import FakeTTSProvider, TTSError
from app.modules.audio.cache import build_cache_key
from app.modules.audio.cache.service import AudioCache, cache_storage_key
from app.modules.audio.facade import build_facade
from app.modules.audio.models import STATUS_FAILED, STATUS_READY, AudioBlob
from tests.test_audio_facade import REGRAS, VOZ, assets_da, nova_historia

SEM_TROCAS = {"base_language": "pt", "segment_types": [], "density": "high"}


@pytest.fixture(autouse=True)
def cache_vazio(db_session):
    """O cache é GLOBAL: blobs que já existam no banco de desenvolvimento (de uso real) mudariam as contagens e
    os acertos. Esvazia-o dentro da transação do teste, que é desfeita no fim (o banco real não é tocado)."""
    db_session.execute(delete(AudioBlob))
    db_session.flush()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def nova(db_session):
    """Cria uma história nova com as mesmas frases (como se fosse de outro usuário ou outra cópia)."""

    def _nova():
        story = nova_historia()
        db_session.add(story)
        db_session.commit()
        return story

    return _nova


@pytest.fixture
def gerar(db_session, storage):
    """Gera a história com as regras e devolve (resultado, provedor falso usado)."""

    def _gerar(story, regras=REGRAS, voz=VOZ, **kwargs):
        tts = FakeTTSProvider()
        facade = build_facade(db_session, tts, storage, voz, sleep=lambda _: None, **kwargs)
        return facade.generate(story.id, regras), tts

    return _gerar


def blobs_de(db_session) -> list[AudioBlob]:
    db_session.expire_all()
    return list(db_session.scalars(select(AudioBlob).order_by(AudioBlob.id)))


# ---------- acerto e erro ----------

def test_erro_de_cache_sintetiza_registra_o_blob_e_vincula_o_asset(nova, gerar, db_session, storage):
    story = nova()
    resultado, tts = gerar(story)

    assert len(tts.calls) == 3 and resultado.cached == [] and resultado.chars_saved == 0
    assets = assets_da(db_session, story)
    blobs = {b.id: b for b in blobs_de(db_session)}
    assert len({a.blob_id for a in assets}) == 3
    for asset in assets:
        blob = blobs[asset.blob_id]
        assert asset.status == STATUS_READY and asset.storage_key == blob.storage_key
        assert (asset.format, asset.duration_ms) == (blob.format, blob.duration_ms)
        assert blob.storage_key == cache_storage_key(blob.cache_key, "wav")
        assert storage.get(blob.storage_key)[:4] == b"RIFF"
        assert blob.size_bytes == len(storage.get(blob.storage_key)) and blob.char_count > 0
        assert (blob.hit_count, blob.miss_count) == (0, 1)


def test_mesma_historia_e_mesmo_filtro_duas_vezes_chama_o_tts_so_na_primeira(nova, gerar):
    story = nova()
    _, primeiro = gerar(story)
    resultado, segundo = gerar(story)

    assert len(primeiro.calls) == 3
    assert segundo.calls == [] and len(resultado.skipped) == 3


def test_outro_filtro_so_chama_o_tts_para_as_frases_cujo_ssml_mudou(nova, gerar, db_session):
    story = nova()
    _, tts_a = gerar(story, REGRAS)  # 2 das 3 frases com troca
    resultado, tts_b = gerar(story, SEM_TROCAS)  # nenhuma troca

    ssml_a = {c.ssml for c in tts_a.calls}
    assert len(tts_b.calls) == 2
    assert all(c.ssml not in ssml_a for c in tts_b.calls)
    assert len(resultado.cached) == 1 and resultado.chars_saved > 0
    # A frase sem troca nos dois filtros usa o MESMO arquivo: 6 assets, 5 blobs
    blob_ids = [a.blob_id for a in assets_da(db_session, story)]
    assert len(blob_ids) == 6 and len(set(blob_ids)) == 5


def test_outro_usuario_com_as_mesmas_frases_reaproveita_tudo(nova, gerar, db_session):
    _, primeiro = gerar(nova(), REGRAS)
    outra = nova()
    resultado, segundo = gerar(outra, REGRAS)

    assert len(primeiro.calls) == 3 and segundo.calls == []
    assert resultado.cached == [s.id for s in outra.segments] and resultado.generated == []
    blobs = blobs_de(db_session)
    assert len(blobs) == 3 and all(b.hit_count == 1 for b in blobs)
    assert resultado.chars_saved == sum(b.char_count for b in blobs)


@pytest.mark.parametrize("mudanca", [{"voz": "outra-voz"}, {"audio_format": "mp3"}, {"provider": "outro"}])
def test_mudar_a_voz_o_formato_ou_o_fornecedor_gera_audio_novo(nova, gerar, mudanca):
    gerar(nova())
    resultado, tts = gerar(nova(), **mudanca)
    assert len(tts.calls) == 3 and resultado.cached == []


def test_blob_com_arquivo_sumido_e_regenerado_e_corrigido(nova, gerar, db_session, storage):
    gerar(nova())
    perdido = blobs_de(db_session)[0]
    storage.delete(perdido.storage_key)

    resultado, tts = gerar(nova())

    assert len(tts.calls) == 1 and len(resultado.cached) == 2 and len(resultado.generated) == 1
    db_session.refresh(perdido)
    assert storage.get(perdido.storage_key)[:4] == b"RIFF"  # o áudio volta a tocar
    assert (perdido.hit_count, perdido.miss_count) == (0, 2)


# ---------- falhas no meio ----------

class ArmazenamentoQueFalha(InMemoryStorage):
    def put(self, key, data, content_type="application/octet-stream"):
        raise StorageError("armazenamento fora do ar")


def test_falha_ao_gravar_nao_deixa_blob_apontando_para_arquivo_inexistente(nova, db_session):
    story = nova()
    facade = build_facade(db_session, FakeTTSProvider(), ArmazenamentoQueFalha(), VOZ, sleep=lambda _: None)
    resultado = facade.generate(story.id, REGRAS)

    assert len(resultado.failed) == 3
    assert all(a.status == STATUS_FAILED and a.blob_id is None for a in assets_da(db_session, story))
    assert blobs_de(db_session) == []


def test_falha_do_tts_nao_registra_blob(nova, db_session, storage):
    class TTSQueFalha(FakeTTSProvider):
        def synthesize(self, ssml, voice_id):
            raise TTSError("SSML recusado")

    resultado = build_facade(db_session, TTSQueFalha(), storage, VOZ).generate(nova().id, REGRAS)
    assert len(resultado.failed) == 3 and blobs_de(db_session) == []


def test_provedor_sem_nome_nem_formato_usa_os_padroes(db_session, storage):
    class ProvedorSimples:
        def synthesize(self, ssml, voice_id):
            return FakeTTSProvider().synthesize(ssml, voice_id)

    facade = build_facade(db_session, ProvedorSimples(), storage, VOZ)
    assert (facade.provider, facade.audio_format) == ("desconhecido", "wav")


# ---------- simultaneidade ----------

class TTSLento(FakeTTSProvider):
    """Provedor falso que demora um pouco: o segundo pedido chega durante a síntese do primeiro."""

    def __init__(self, espera: float) -> None:
        super().__init__()
        self.espera = espera
        self._lock = threading.Lock()

    def synthesize(self, ssml, voice_id):
        time.sleep(self.espera)
        with self._lock:
            return super().synthesize(ssml, voice_id)


@pytest.mark.parametrize("rodada", range(20))  # 20 vezes seguidas: o teste não pode ser instável
def test_dois_pedidos_simultaneos_da_mesma_frase_chamam_o_tts_uma_vez(db_session, rodada):
    from app.core.database import engine

    ssml = f'<speak version="1.0" xml:lang="pt-BR">Frase nova {uuid.uuid4().hex}.</speak>'
    tts = TTSLento(espera=0.05)
    storage = InMemoryStorage()
    barreira = threading.Barrier(2)
    resultados: list[tuple[int, bool]] = []
    erros: list[BaseException] = []

    def pedir():
        try:
            with Session(engine) as db:
                barreira.wait(timeout=10)
                r = AudioCache(db, storage).fetch_or_create(
                    ssml, voice_id=VOZ, provider="fake", audio_format="wav",
                    synthesize=lambda: tts.synthesize(ssml, VOZ),
                )
                resultados.append((r.blob.id, r.hit))
        except BaseException as exc:  # noqa: BLE001 - o erro da thread precisa chegar ao teste
            erros.append(exc)

    try:
        threads = [threading.Thread(target=pedir) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert erros == []
        assert len(tts.calls) == 1
        assert len(resultados) == 2 and resultados[0][0] == resultados[1][0]
        assert sorted(hit for _, hit in resultados) == [False, True]
    finally:
        with Session(engine) as db:
            db.execute(delete(AudioBlob).where(AudioBlob.cache_key == build_cache_key(ssml, VOZ, "fake", "wav")))
            db.commit()
