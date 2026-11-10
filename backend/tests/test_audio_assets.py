"""Testes do modelo AudioAsset, da migração e do AudioAssetRepository (#84).

Escritos antes do código (TDD). Usam o banco de teste (`db_session`, desfeito no fim de cada teste), menos o
teste de concorrência, que precisa de conexões de verdade e apaga o que criou no final.
"""
import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.modules.audio.models import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
    STATUS_READY,
    AudioAsset,
)
from app.modules.audio.repository import AudioAssetRepository, InvalidTransition, compute_rules_hash
from app.modules.stories.models import Segment, Story

REGRAS = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "medium"}
HASH = compute_rules_hash(REGRAS)
VOZ = "pt-BR-ThalitaMultilingualNeural"


def nova_historia(n_frases: int = 3) -> Story:
    return Story(
        title="A raposa e as uvas",
        segments=[
            Segment(position=i, text_en=f"Sentence {i}.", text_pt=f"Frase {i}.") for i in range(n_frases)
        ],
    )


@pytest.fixture
def historia(db_session) -> Story:
    story = nova_historia()
    db_session.add(story)
    db_session.commit()
    return story


@pytest.fixture
def repo(db_session) -> AudioAssetRepository:
    return AudioAssetRepository(db_session)


def criar(repo: AudioAssetRepository, historia: Story, posicao: int = 0, rules_hash: str = HASH, voz: str = VOZ):
    segmento = historia.segments[posicao]
    return repo.get_or_create(
        story_id=historia.id, segment_id=segmento.id, rules_hash=rules_hash, voice_id=voz
    )


def total(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(AudioAsset))


# ---------- hash das regras ----------

def test_o_hash_das_regras_nao_depende_da_ordem_das_chaves():
    mesma_regra = {"density": "medium", "segment_types": ["phrasal_verbs"], "base_language": "pt"}
    assert compute_rules_hash(mesma_regra) == HASH


def test_regras_diferentes_tem_hash_diferente():
    assert compute_rules_hash({**REGRAS, "density": "high"}) != HASH


def test_o_hash_e_um_sha256_em_hexadecimal():
    assert len(HASH) == 64 and all(c in "0123456789abcdef" for c in HASH)


# ---------- get_or_create ----------

def test_cria_o_audio_como_pendente(repo, historia):
    asset = criar(repo, historia)

    assert asset.id is not None
    assert asset.status == STATUS_PENDING
    assert asset.story_id == historia.id
    assert asset.segment_id == historia.segments[0].id
    assert (asset.rules_hash, asset.voice_id) == (HASH, VOZ)
    assert asset.storage_key is None and asset.duration_ms is None
    assert asset.attempts == 0


def test_pedir_de_novo_devolve_o_mesmo_registro(repo, historia, db_session):
    primeiro = criar(repo, historia)
    segundo = criar(repo, historia)

    assert primeiro.id == segundo.id
    assert total(db_session) == 1


def test_pedir_de_novo_nao_desfaz_o_que_ja_esta_pronto(repo, historia):
    asset = criar(repo, historia)
    repo.start_generation(asset)
    repo.mark_ready(asset, storage_key="audio/1.mp3", audio_format="mp3", duration_ms=1200)

    assert criar(repo, historia).status == STATUS_READY


@pytest.mark.parametrize(
    "diferenca",
    [{"posicao": 1}, {"rules_hash": compute_rules_hash({**REGRAS, "density": "high"})}, {"voz": "outra-voz"}],
    ids=["outra-frase", "outras-regras", "outra-voz"],
)
def test_mudar_frase_regras_ou_voz_cria_outro_registro(repo, historia, db_session, diferenca):
    um = criar(repo, historia)
    outro = criar(repo, historia, **diferenca)

    assert um.id != outro.id
    assert total(db_session) == 2


def test_o_banco_recusa_dois_registros_para_a_mesma_frase_regras_e_voz(db_session, historia):
    segmento = historia.segments[0]
    for _ in range(2):
        db_session.add(AudioAsset(story_id=historia.id, segment_id=segmento.id, rules_hash=HASH, voice_id=VOZ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------- apagar a história ----------

def test_apagar_a_historia_apaga_os_audios(repo, historia, db_session):
    criar(repo, historia, 0)
    criar(repo, historia, 1)

    db_session.delete(historia)
    db_session.commit()

    assert total(db_session) == 0


def test_apagar_a_historia_direto_no_banco_tambem_apaga_os_audios(repo, historia, db_session):
    """O CASCADE é do banco, não só do ORM: vale para um DELETE feito por fora."""
    criar(repo, historia)
    db_session.execute(text("DELETE FROM stories WHERE id = :id"), {"id": historia.id})
    db_session.commit()
    assert total(db_session) == 0


# ---------- transições de estado ----------

def test_caminho_feliz_pendente_gerando_pronto(repo, historia, db_session):
    asset = criar(repo, historia)

    repo.start_generation(asset)
    assert asset.status == STATUS_GENERATING
    assert asset.attempts == 1

    repo.mark_ready(asset, storage_key="audio/1/0.mp3", audio_format="mp3", duration_ms=2300)
    db_session.expire_all()  # lê de novo do banco: o que vale é o que foi gravado
    salvo = db_session.get(AudioAsset, asset.id)
    assert salvo.status == STATUS_READY
    assert (salvo.storage_key, salvo.format, salvo.duration_ms) == ("audio/1/0.mp3", "mp3", 2300)
    assert salvo.error is None


def test_falha_guarda_o_erro_e_pode_voltar_a_pendente(repo, historia):
    asset = criar(repo, historia)
    repo.start_generation(asset)

    repo.mark_failed(asset, "Azure TTS respondeu 503")
    assert asset.status == STATUS_FAILED
    assert asset.error == "Azure TTS respondeu 503"

    repo.reset_to_pending(asset)
    assert asset.status == STATUS_PENDING


def test_falha_pode_ser_gerada_de_novo_e_conta_as_tentativas(repo, historia):
    asset = criar(repo, historia)
    repo.start_generation(asset)
    repo.mark_failed(asset, "tempo esgotado")

    repo.start_generation(asset)
    assert asset.status == STATUS_GENERATING
    assert asset.attempts == 2


def test_ficar_pronto_limpa_o_erro_anterior(repo, historia):
    asset = criar(repo, historia)
    repo.start_generation(asset)
    repo.mark_failed(asset, "tempo esgotado")
    repo.start_generation(asset)
    repo.mark_ready(asset, storage_key="a.mp3", audio_format="mp3", duration_ms=10)
    assert asset.error is None


@pytest.mark.parametrize(
    ("preparar", "transicao_invalida"),
    [
        ("pronto", "start_generation"),  # ready -> generating: o exemplo da issue
        ("pronto", "reset_to_pending"),  # ready -> pending
        ("pronto", "mark_failed"),  # ready -> failed
        ("pendente", "mark_ready"),  # pending -> ready, sem passar por generating
        ("pendente", "mark_failed"),  # pending -> failed
    ],
)
def test_transicao_invalida_e_recusada_e_nada_muda(repo, historia, db_session, preparar, transicao_invalida):
    asset = criar(repo, historia)
    if preparar == "pronto":
        repo.start_generation(asset)
        repo.mark_ready(asset, storage_key="a.mp3", audio_format="mp3", duration_ms=10)
    antes = asset.status

    argumentos = {
        "start_generation": {},
        "reset_to_pending": {},
        "mark_failed": {"error": "x"},
        "mark_ready": {"storage_key": "b.mp3", "audio_format": "mp3", "duration_ms": 20},
    }[transicao_invalida]
    with pytest.raises(InvalidTransition):
        getattr(repo, transicao_invalida)(asset, **argumentos)

    db_session.expire_all()
    assert db_session.get(AudioAsset, asset.id).status == antes


def test_transicao_recusada_se_outro_processo_mudou_o_estado_antes(repo, historia, db_session):
    """Dois workers pegam a mesma frase pendente: só o primeiro começa a gerar."""
    asset = criar(repo, historia)
    # Outro processo começa a gerar por fora, sem que este objeto saiba
    db_session.execute(
        update(AudioAsset).where(AudioAsset.id == asset.id).values(status=STATUS_GENERATING),
        execution_options={"synchronize_session": False},
    )
    db_session.commit()

    with pytest.raises(InvalidTransition):
        repo.start_generation(asset)


def test_o_banco_recusa_status_desconhecido(db_session, historia):
    db_session.add(
        AudioAsset(
            story_id=historia.id, segment_id=historia.segments[0].id, rules_hash=HASH, voice_id=VOZ,
            status="quase-pronto",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_o_banco_recusa_pronto_sem_arquivo(db_session, historia):
    db_session.add(
        AudioAsset(
            story_id=historia.id, segment_id=historia.segments[0].id, rules_hash=HASH, voice_id=VOZ,
            status=STATUS_READY,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_mark_ready_recusa_duracao_negativa(repo, historia):
    asset = criar(repo, historia)
    repo.start_generation(asset)
    with pytest.raises(ValueError):
        repo.mark_ready(asset, storage_key="a.mp3", audio_format="mp3", duration_ms=-1)


# ---------- consultas ----------

def test_list_by_story_devolve_na_ordem_das_frases_e_so_do_filtro_e_voz_pedidos(repo, historia):
    criar(repo, historia, 2)
    criar(repo, historia, 0)
    criar(repo, historia, 1)
    criar(repo, historia, 0, voz="outra-voz")
    criar(repo, historia, 0, rules_hash=compute_rules_hash({**REGRAS, "density": "high"}))

    assets = repo.list_by_story(historia.id, rules_hash=HASH, voice_id=VOZ)

    posicoes = {s.id: s.position for s in historia.segments}
    assert [posicoes[a.segment_id] for a in assets] == [0, 1, 2]


def test_get_devolve_o_registro_ou_none(repo, historia):
    asset = criar(repo, historia)
    assert repo.get(asset.id).id == asset.id
    assert repo.get(999_999_999) is None


# ---------- frases presas em "gerando" ----------

def envelhecer(db_session, asset: AudioAsset, minutos: int) -> None:
    """Faz de conta que o registro foi alterado há `minutos` minutos."""
    db_session.execute(
        update(AudioAsset)
        .where(AudioAsset.id == asset.id)
        .values(updated_at=func.now() - timedelta(minutes=minutos)),
        execution_options={"synchronize_session": False},
    )
    db_session.commit()


def test_reset_stale_volta_para_pendente_so_o_que_esta_preso_ha_mais_tempo(repo, historia, db_session):
    preso, recente, pronto_antigo = (criar(repo, historia, i) for i in range(3))
    for asset in (preso, recente, pronto_antigo):
        repo.start_generation(asset)
    repo.mark_ready(pronto_antigo, storage_key="a.mp3", audio_format="mp3", duration_ms=10)

    envelhecer(db_session, preso, 30)
    envelhecer(db_session, pronto_antigo, 30)
    envelhecer(db_session, recente, 2)

    assert repo.reset_stale(older_than=timedelta(minutes=10)) == 1

    db_session.expire_all()
    assert db_session.get(AudioAsset, preso.id).status == STATUS_PENDING
    assert db_session.get(AudioAsset, recente.id).status == STATUS_GENERATING
    assert db_session.get(AudioAsset, pronto_antigo.id).status == STATUS_READY


def test_reset_stale_sem_nada_preso_devolve_zero(repo, historia):
    criar(repo, historia)
    assert repo.reset_stale(older_than=timedelta(minutes=10)) == 0


# ---------- concorrência ----------

def test_get_or_create_e_seguro_com_chamadas_simultaneas(db_session):
    """8 chamadas ao mesmo tempo, cada uma na sua conexão, criam um único registro.

    Precisa de transações de verdade (o `db_session` só garante que o banco está no ar): a história é
    gravada de fato e apagada no fim, levando os áudios junto (CASCADE).
    """
    from app.core.database import SessionLocal

    with SessionLocal() as sessao:
        story = nova_historia(1)
        sessao.add(story)
        sessao.commit()
        story_id, segment_id = story.id, story.segments[0].id

    n = 8
    largada = threading.Barrier(n)
    ids: list[int] = []
    erros: list[Exception] = []

    def chamar():
        with SessionLocal() as sessao:
            largada.wait()  # todas as threads chamam ao mesmo tempo
            try:
                asset = AudioAssetRepository(sessao).get_or_create(
                    story_id=story_id, segment_id=segment_id, rules_hash=HASH, voice_id=VOZ
                )
                ids.append(asset.id)
            except Exception as exc:  # noqa: BLE001 - o teste mostra qualquer erro
                erros.append(exc)

    try:
        threads = [threading.Thread(target=chamar) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert erros == []
        assert len(ids) == n and len(set(ids)) == 1
        with SessionLocal() as sessao:
            quantos = sessao.scalar(
                select(func.count()).select_from(AudioAsset).where(AudioAsset.segment_id == segment_id)
            )
        assert quantos == 1
    finally:
        with SessionLocal() as sessao:
            sessao.execute(text("DELETE FROM stories WHERE id = :id"), {"id": story_id})
            sessao.commit()

