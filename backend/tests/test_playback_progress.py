"""Testes do modelo PlaybackProgress, da migração e do PlaybackProgressRepository (#95).

Escritos antes do código (TDD). Usam o banco de teste (`db_session`, desfeito no fim de cada teste), menos o
teste de concorrência, que precisa de conexões de verdade e apaga o que criou no final.
"""
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.modules.filters.models import ListeningFilter
from app.modules.progress.models import PlaybackProgress
from app.modules.progress.repository import PlaybackProgressRepository
from app.modules.stories.models import Segment, Story
from app.modules.users.models import User

AGORA = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def novo_usuario(nome: str = "Ana") -> User:
    return User(name=nome, email=f"{uuid.uuid4().hex}@teste.com", password_hash="x")


def nova_historia(titulo: str = "A raposa e as uvas", n_frases: int = 5) -> Story:
    return Story(
        title=titulo,
        segments=[Segment(position=i, text_en=f"Sentence {i}.", text_pt=f"Frase {i}.") for i in range(n_frases)],
    )


@pytest.fixture
def usuario(db_session) -> User:
    user = novo_usuario()
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def historia(db_session) -> Story:
    story = nova_historia()
    db_session.add(story)
    db_session.commit()
    return story


@pytest.fixture
def filtro(db_session, usuario) -> ListeningFilter:
    listening_filter = ListeningFilter(user_id=usuario.id, rules={"base_language": "pt", "density": "medium"})
    db_session.add(listening_filter)
    db_session.commit()
    return listening_filter


@pytest.fixture
def repo(db_session) -> PlaybackProgressRepository:
    return PlaybackProgressRepository(db_session)


def salvar(repo, usuario, historia, frase=2, offset=1500, quando=AGORA, **kwargs) -> PlaybackProgress:
    return repo.upsert(
        user_id=usuario.id,
        story_id=historia.id,
        segment_position=frase,
        offset_ms=offset,
        client_time=quando,
        **kwargs,
    )


def total(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(PlaybackProgress))


# ---------- upsert ----------

def test_a_primeira_gravacao_cria_o_progresso(repo, usuario, historia, filtro):
    progresso = salvar(repo, usuario, historia, frase=2, offset=1500, filter_id=filtro.id)

    assert progresso.id is not None
    assert (progresso.user_id, progresso.story_id, progresso.filter_id) == (usuario.id, historia.id, filtro.id)
    assert (progresso.segment_position, progresso.offset_ms) == (2, 1500)
    assert progresso.completed is False
    assert progresso.client_time == AGORA


def test_o_filtro_e_opcional(repo, usuario, historia):
    assert salvar(repo, usuario, historia).filter_id is None


def test_gravar_de_novo_atualiza_o_mesmo_registro(repo, usuario, historia, db_session):
    primeiro = salvar(repo, usuario, historia, frase=1, offset=0)
    segundo = salvar(repo, usuario, historia, frase=3, offset=700, quando=AGORA + timedelta(seconds=5))

    assert primeiro.id == segundo.id
    assert (segundo.segment_position, segundo.offset_ms) == (3, 700)
    assert total(db_session) == 1


def test_gravar_a_mesma_posicao_varias_vezes_nao_duplica(repo, usuario, historia, db_session):
    for _ in range(5):
        salvar(repo, usuario, historia)
    assert total(db_session) == 1


def test_marcar_como_concluida(repo, usuario, historia):
    salvar(repo, usuario, historia, frase=1)
    progresso = salvar(repo, usuario, historia, frase=4, offset=900, quando=AGORA + timedelta(minutes=3), completed=True)
    assert progresso.completed is True


def test_usuarios_diferentes_tem_progressos_separados(repo, usuario, historia, db_session):
    outro = novo_usuario("Bia")
    db_session.add(outro)
    db_session.commit()

    meu = salvar(repo, usuario, historia, frase=1)
    dele = salvar(repo, outro, historia, frase=4)

    assert meu.id != dele.id
    assert repo.get(usuario.id, historia.id).segment_position == 1
    assert repo.get(outro.id, historia.id).segment_position == 4


def test_o_banco_recusa_dois_progressos_do_mesmo_usuario_na_mesma_historia(db_session, usuario, historia):
    for _ in range(2):
        db_session.add(
            PlaybackProgress(
                user_id=usuario.id, story_id=historia.id, segment_position=0, offset_ms=0, client_time=AGORA
            )
        )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------- gravações fora de ordem ----------

def test_uma_gravacao_mais_antiga_nao_sobrescreve_a_mais_nova(repo, usuario, historia):
    """O front envia a cada 5 s: uma requisição atrasada não pode voltar o usuário para trás."""
    salvar(repo, usuario, historia, frase=4, offset=200, quando=AGORA)
    resultado = salvar(repo, usuario, historia, frase=1, offset=0, quando=AGORA - timedelta(seconds=10))

    assert (resultado.segment_position, resultado.offset_ms) == (4, 200)  # devolve o que ficou valendo
    assert resultado.client_time == AGORA
    assert repo.get(usuario.id, historia.id).segment_position == 4


def test_uma_gravacao_com_o_mesmo_horario_atualiza(repo, usuario, historia):
    salvar(repo, usuario, historia, frase=1, quando=AGORA)
    assert salvar(repo, usuario, historia, frase=2, quando=AGORA).segment_position == 2


# ---------- get e delete ----------

def test_get_sem_progresso_devolve_none(repo, usuario, historia):
    assert repo.get(usuario.id, historia.id) is None


def test_delete_apaga_o_progresso_para_recomecar(repo, usuario, historia):
    salvar(repo, usuario, historia)
    assert repo.delete(usuario.id, historia.id) is True
    assert repo.get(usuario.id, historia.id) is None


def test_delete_sem_progresso_devolve_false(repo, usuario, historia):
    assert repo.delete(usuario.id, historia.id) is False


def test_delete_so_apaga_o_progresso_do_proprio_usuario(repo, usuario, historia, db_session):
    outro = novo_usuario("Bia")
    db_session.add(outro)
    db_session.commit()
    salvar(repo, usuario, historia)
    salvar(repo, outro, historia)

    repo.delete(usuario.id, historia.id)

    assert repo.get(outro.id, historia.id) is not None


# ---------- o que acontece ao apagar usuário, história ou filtro ----------

def test_apagar_o_usuario_apaga_o_progresso(repo, usuario, historia, db_session):
    salvar(repo, usuario, historia)
    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": usuario.id})
    db_session.commit()
    assert total(db_session) == 0


def test_apagar_a_historia_apaga_o_progresso(repo, usuario, historia, db_session):
    salvar(repo, usuario, historia)
    db_session.execute(text("DELETE FROM stories WHERE id = :id"), {"id": historia.id})
    db_session.commit()
    assert total(db_session) == 0


def test_apagar_o_filtro_mantem_o_progresso_sem_filtro(repo, usuario, historia, filtro, db_session):
    salvar(repo, usuario, historia, frase=3, filter_id=filtro.id)
    db_session.execute(text("DELETE FROM listening_filters WHERE id = :id"), {"id": filtro.id})
    db_session.commit()

    db_session.expire_all()
    progresso = repo.get(usuario.id, historia.id)
    assert progresso is not None
    assert progresso.filter_id is None
    assert progresso.segment_position == 3


# ---------- valores inválidos ----------

@pytest.mark.parametrize(("frase", "offset"), [(-1, 0), (0, -1)], ids=["frase-negativa", "offset-negativo"])
def test_o_banco_recusa_valores_negativos(db_session, usuario, historia, frase, offset):
    db_session.add(
        PlaybackProgress(
            user_id=usuario.id, story_id=historia.id, segment_position=frase, offset_ms=offset, client_time=AGORA
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------- list_recent ----------

@pytest.fixture
def tres_historias(db_session) -> list[Story]:
    stories = [nova_historia(f"História {i}") for i in range(3)]
    db_session.add_all(stories)
    db_session.commit()
    return stories


def test_list_recent_devolve_do_mais_recente_para_o_mais_antigo(repo, usuario, tres_historias):
    antiga, recente, meio = tres_historias
    salvar(repo, usuario, antiga, quando=AGORA - timedelta(days=2))
    salvar(repo, usuario, recente, quando=AGORA)
    salvar(repo, usuario, meio, quando=AGORA - timedelta(hours=3))

    assert [p.story_id for p in repo.list_recent(usuario.id)] == [recente.id, meio.id, antiga.id]


def test_list_recent_respeita_o_limite(repo, usuario, tres_historias):
    for i, story in enumerate(tres_historias):
        salvar(repo, usuario, story, quando=AGORA - timedelta(hours=i))
    assert [p.story_id for p in repo.list_recent(usuario.id, limit=2)] == [s.id for s in tres_historias[:2]]


def test_list_recent_deixa_de_fora_as_concluidas_por_padrao(repo, usuario, tres_historias):
    em_andamento, concluida, _ = tres_historias
    salvar(repo, usuario, em_andamento, quando=AGORA - timedelta(hours=1))
    salvar(repo, usuario, concluida, quando=AGORA, completed=True)

    assert [p.story_id for p in repo.list_recent(usuario.id)] == [em_andamento.id]
    assert [p.story_id for p in repo.list_recent(usuario.id, include_completed=True)] == [
        concluida.id,
        em_andamento.id,
    ]


def test_list_recent_so_traz_o_progresso_do_proprio_usuario(repo, usuario, historia, db_session):
    outro = novo_usuario("Bia")
    db_session.add(outro)
    db_session.commit()
    salvar(repo, outro, historia)

    assert repo.list_recent(usuario.id) == []


def test_list_recent_recusa_limite_invalido(repo, usuario):
    with pytest.raises(ValueError):
        repo.list_recent(usuario.id, limit=0)


# ---------- concorrência ----------

def test_upsert_e_seguro_com_chamadas_simultaneas(db_session):
    """8 gravações ao mesmo tempo, cada uma na sua conexão, ficam num único registro, e vale a mais nova.

    Precisa de transações de verdade (o `db_session` só garante que o banco está no ar): o usuário e a
    história são gravados de fato e apagados no fim, levando o progresso junto (CASCADE).
    """
    from app.core.database import SessionLocal

    with SessionLocal() as sessao:
        user, story = novo_usuario(), nova_historia(n_frases=10)
        sessao.add_all([user, story])
        sessao.commit()
        user_id, story_id = user.id, story.id

    n = 8
    largada = threading.Barrier(n)
    erros: list[Exception] = []

    def gravar(i: int):
        with SessionLocal() as sessao:
            largada.wait()  # todas as threads gravam ao mesmo tempo
            try:
                PlaybackProgressRepository(sessao).upsert(
                    user_id=user_id,
                    story_id=story_id,
                    segment_position=i,
                    offset_ms=0,
                    client_time=AGORA + timedelta(seconds=i),  # a thread 7 é a gravação mais nova
                )
            except Exception as exc:  # noqa: BLE001 - o teste mostra qualquer erro
                erros.append(exc)

    try:
        threads = [threading.Thread(target=gravar, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert erros == []
        with SessionLocal() as sessao:
            registros = list(
                sessao.scalars(
                    select(PlaybackProgress).where(
                        PlaybackProgress.user_id == user_id, PlaybackProgress.story_id == story_id
                    )
                )
            )
        assert len(registros) == 1
        assert registros[0].segment_position == n - 1  # a mais nova venceu, qualquer que seja a ordem de chegada
    finally:
        with SessionLocal() as sessao:
            sessao.execute(text("DELETE FROM stories WHERE id = :id"), {"id": story_id})
            sessao.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
            sessao.commit()
