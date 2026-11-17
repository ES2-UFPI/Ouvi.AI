"""Testes dos comandos do cache de áudio (US08): `stats` (#92) e `purge` (#93).

Chamam o `main()` do comando com a sessão de teste e o armazenamento em memória injetados.
"""
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.integrations.storage import InMemoryStorage, StorageError
from app.integrations.tts import FakeTTSProvider
from app.modules.audio.cache.__main__ import main
from app.modules.audio.cache.purge import parse_size, purge
from app.modules.audio.cache.stats import compute_stats, format_size
from app.modules.audio.facade import build_facade
from app.modules.audio.models import STATUS_PENDING, STATUS_READY, AudioAsset, AudioBlob
from tests.test_audio_facade import REGRAS, VOZ, assets_da, nova_historia

AGORA = datetime.now(timezone.utc)


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def gerar(db_session, storage):
    def _gerar():
        story = nova_historia()
        db_session.add(story)
        db_session.commit()
        tts = FakeTTSProvider()
        build_facade(db_session, tts, storage, VOZ).generate(story.id, REGRAS)
        return story, tts

    return _gerar


class _SessaoSemClose:
    def __init__(self, session) -> None:
        self._session = session
        self.fechada = False

    def close(self) -> None:
        self.fechada = True

    def __getattr__(self, nome):
        return getattr(self._session, nome)


@pytest.fixture
def rodar(db_session, storage):
    """Roda o comando e devolve (código de saída, texto impresso)."""

    def _rodar(*argv, **kwargs):
        out = io.StringIO()
        # O comando fecha a sessão no fim; a do teste continua sendo usada depois, então o close não faz nada
        sessao = _SessaoSemClose(db_session)
        code = main(list(argv), session_factory=lambda: sessao, storage=storage, out=out, **kwargs)
        return code, out.getvalue()

    return _rodar


def blobs_de(db_session) -> list[AudioBlob]:
    db_session.expire_all()
    return list(db_session.scalars(select(AudioBlob).order_by(AudioBlob.id)))


def envelhecer(db_session, blob: AudioBlob, dias: int) -> None:
    db_session.execute(
        update(AudioBlob).where(AudioBlob.id == blob.id).values(last_used_at=AGORA - timedelta(days=dias))
    )
    db_session.commit()


def snapshot(db_session):
    db_session.expire_all()
    return [
        (b.id, b.hit_count, b.miss_count, b.last_used_at, b.storage_key) for b in blobs_de(db_session)
    ], [(a.id, a.status, a.blob_id) for a in db_session.scalars(select(AudioAsset).order_by(AudioAsset.id))]


# ---------- stats (#92) ----------

def test_stats_com_o_cache_vazio_mostra_zeros(rodar, db_session):
    for blob in blobs_de(db_session):  # o banco de teste pode ter blobs de outro uso: começa vazio
        db_session.delete(blob)
    db_session.commit()

    code, saida = rodar("stats", "--json", cost_per_1k_chars=0.0)
    assert code == 0
    dados = json.loads(saida)
    assert {k: dados[k] for k in ("files", "size_bytes", "hits", "misses", "chars_saved")} == dict.fromkeys(
        ("files", "size_bytes", "hits", "misses", "chars_saved"), 0
    )
    assert dados["hit_rate"] == 0.0 and dados["cost_saved"] == 0.0

    code, texto = rodar("stats", cost_per_1k_chars=0.0)
    assert code == 0 and "Arquivos:                 0" in texto and "Taxa de acerto:           0.0%" in texto


def test_stats_mostra_acertos_taxa_e_caracteres_economizados(gerar, rodar, db_session):
    for blob in blobs_de(db_session):
        db_session.delete(blob)
    db_session.commit()
    gerar()
    gerar()  # outra história com as mesmas frases: 3 acertos

    blobs = blobs_de(db_session)
    economizados = sum(b.char_count for b in blobs)
    code, saida = rodar("stats", "--json", cost_per_1k_chars=2.0)
    dados = json.loads(saida)
    assert code == 0
    assert (dados["files"], dados["hits"], dados["misses"]) == (3, 3, 3)
    assert dados["hit_rate"] == 0.5
    assert dados["chars_saved"] == economizados
    assert dados["size_bytes"] == sum(b.size_bytes for b in blobs)
    assert dados["cost_saved"] == pytest.approx(economizados / 1000 * 2.0, abs=1e-4)

    _, texto = rodar("stats", cost_per_1k_chars=2.0)
    assert "Acertos:                  3" in texto and "50.0%" in texto and str(economizados) in texto


def test_stats_sem_custo_configurado_mostra_custo_zerado(gerar, db_session):
    gerar()
    gerar()
    assert compute_stats(db_session).cost_saved == 0.0


def test_stats_usa_a_configuracao_quando_o_custo_nao_e_passado(rodar, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tts_cost_per_1k_chars", 0.0)
    code, saida = rodar("stats", "--json")
    assert code == 0 and json.loads(saida)["cost_per_1k_chars"] == 0.0


def test_stats_so_le_sem_alterar_o_banco(gerar, rodar, db_session):
    gerar()
    gerar()
    antes = snapshot(db_session)
    rodar("stats")
    rodar("stats", "--json")
    assert snapshot(db_session) == antes


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(1536) == "1.5 KB"
    assert format_size(3 * 1024**2) == "3.0 MB"
    assert format_size(5 * 1024**3) == "5.0 GB"


# ---------- purge (#93) ----------

def test_parse_size():
    assert parse_size("500MB") == 500 * 1024**2
    assert parse_size("1.5gb") == int(1.5 * 1024**3)
    assert parse_size("2048") == 2048
    assert parse_size("10 KB") == 10240
    with pytest.raises(ValueError):
        parse_size("muito")


def test_purge_sem_opcoes_nao_apaga_nada(gerar, rodar, db_session):
    gerar()
    antes = snapshot(db_session)
    code, saida = rodar("purge")
    assert code == 0 and "Nada a fazer" in saida
    assert snapshot(db_session) == antes


def test_older_than_remove_so_o_que_nao_e_usado_ha_mais_que_o_prazo(gerar, rodar, db_session, storage):
    story, _ = gerar()
    velho, novo1, novo2 = blobs_de(db_session)[-3:]
    envelhecer(db_session, velho, 40)
    envelhecer(db_session, novo1, 10)
    velho_id, velho_arquivo, novos = velho.id, velho.storage_key, {novo1.id, novo2.id}

    code, saida = rodar("purge", "--older-than", "30")

    assert code == 0 and "removidos" in saida
    restantes = {b.id for b in blobs_de(db_session)}
    assert velho_id not in restantes and novos <= restantes
    with pytest.raises(StorageError):
        storage.get(velho_arquivo)
    assets = assets_da(db_session, story)
    voltaram = [a for a in assets if a.status == STATUS_PENDING]
    assert len(voltaram) == 1 and voltaram[0].storage_key is None and voltaram[0].blob_id is None
    assert sum(a.status == STATUS_READY for a in assets) == 2


def test_assets_afetados_voltam_para_pending_e_gerar_de_novo_recria_o_audio(gerar, db_session, storage):
    story, _ = gerar()
    for blob in blobs_de(db_session):
        envelhecer(db_session, blob, 100)
    relatorio = purge(db_session, storage, older_than_days=30)
    assert relatorio.assets_reset >= 3

    tts = FakeTTSProvider()
    resultado = build_facade(db_session, tts, storage, VOZ).generate(story.id, REGRAS)
    assert len(tts.calls) == 3 and len(resultado.generated) == 3
    assert all(storage.get(a.storage_key)[:4] == b"RIFF" for a in assets_da(db_session, story))


def test_max_size_remove_os_menos_recentes_ate_caber(gerar, db_session, storage):
    gerar()
    for blob in blobs_de(db_session):
        envelhecer(db_session, blob, 1000)  # blobs de fora deste teste também saem primeiro
    a, b, c = blobs_de(db_session)[-3:]
    envelhecer(db_session, a, 3)
    envelhecer(db_session, b, 2)
    envelhecer(db_session, c, 1)

    relatorio = purge(db_session, storage, max_size_bytes=c.size_bytes)

    restantes = blobs_de(db_session)
    assert [x.id for x in restantes] == [c.id]
    assert relatorio.freed_bytes == sum(x.size_bytes for x in relatorio.blobs)
    assert [x.blob_id for x in relatorio.blobs][-2:] == [a.id, b.id]  # do menos recente para o mais recente


def test_dry_run_nao_altera_nada_e_mostra_o_relatorio(gerar, rodar, db_session, storage):
    gerar()
    for blob in blobs_de(db_session):
        envelhecer(db_session, blob, 100)
    antes = snapshot(db_session)

    code, saida = rodar("purge", "--older-than", "30", "--max-size", "1KB", "--dry-run")
    assert code == 0 and "simulação" in saida and "seriam removidos" in saida
    code, saida_json = rodar("purge", "--older-than", "30", "--dry-run", "--json")
    dados = json.loads(saida_json)
    assert dados["dry_run"] is True and dados["removed"] >= 3 and dados["assets_reset"] >= 3

    assert snapshot(db_session) == antes
    assert all(storage.get(b.storage_key) for b in blobs_de(db_session)[-3:])


class ArmazenamentoQueNaoApaga(InMemoryStorage):
    def delete(self, key):
        raise StorageError("armazenamento fora do ar")


def test_falha_ao_apagar_o_arquivo_nao_deixa_registro_apontando_para_arquivo_inexistente(gerar, db_session):
    story, _ = gerar()
    for blob in blobs_de(db_session):
        envelhecer(db_session, blob, 100)

    relatorio = purge(db_session, ArmazenamentoQueNaoApaga(), older_than_days=30)

    assert relatorio.file_errors and blobs_de(db_session) == []
    assert all(a.status == STATUS_PENDING and a.storage_key is None for a in assets_da(db_session, story))


def test_purge_recusa_valores_negativos(rodar, db_session, storage):
    code, saida = rodar("purge", "--older-than", "-1")
    assert code == 2 and "negativo" in saida
    with pytest.raises(ValueError):
        purge(db_session, storage, max_size_bytes=-1)
