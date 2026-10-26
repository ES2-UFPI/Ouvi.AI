"""Testes do TextAnnotator e do comando de anotação, no banco de dados.

Cada teste roda numa transação que é desfeita no final (veja `db_session` no conftest), então os
dados do ambiente de desenvolvimento não são alterados. Precisam do Postgres no ar e migrado.
"""
from unittest import mock

import pytest
from sqlalchemy import select

from app.modules.stories import annotate
from app.modules.stories.annotator import TextAnnotator
from app.modules.stories.models import Annotation, Segment, Story
from app.modules.stories.repository import (
    AnnotationRepository,
    SegmentRepository,
    StoryRepository,
)
from app.modules.stories.seed.loader import load_seed
from app.modules.stories.seed.validation import read_seed_files

# (inglês, português)
DESISTIR = ("They gave up after two hours.", "Eles desistiram depois de duas horas.")
ACORDAR = ("She woke up early this morning.", "Ela acordou cedo nesta manhã.")
VESTIR = ("He put on his coat.", "Ele vestiu o casaco.")  # 'put on' não está no dicionário
SEM_NADA = ("The cat is sleeping.", "O gato está dormindo.")


def criar_historia(db, titulo: str, frases: list[tuple[str, str]]) -> int:
    story = StoryRepository(db).create(titulo, None, "en")
    for posicao, (en, pt) in enumerate(frases):
        SegmentRepository(db).create(story.id, posicao, en, pt)
    return story.id


def anotacoes(db, story_id: int) -> list[Annotation]:
    db.expire_all()
    stmt = (
        select(Annotation)
        .join(Segment, Segment.id == Annotation.segment_id)
        .where(Segment.story_id == story_id)
        .order_by(Segment.position, Annotation.en_start)
    )
    return list(db.scalars(stmt))


def assinatura(db, story_id: int) -> list[tuple]:
    return [(a.segment_id, a.lemma, a.en_start, a.en_end, a.pt_start, a.pt_end) for a in anotacoes(db, story_id)]


@pytest.fixture
def annotator(db_session) -> TextAnnotator:
    return TextAnnotator.with_defaults(db_session)


# ---------- anotar e alinhar ----------

def test_detecta_alinha_e_registra_o_que_ficou_sem_equivalente(db_session, annotator):
    sid = criar_historia(db_session, "TESTE-anotar", [DESISTIR, ACORDAR, VESTIR, SEM_NADA])

    report = annotator.annotate_story(sid)

    assert (report.segments, report.detected, report.aligned, report.unaligned) == (4, 3, 2, 1)
    assert [(i.position, i.lemma, i.en_text) for i in report.unaligned_items] == [(2, "put on", "put on")]

    por_lema = {a.lemma: a for a in anotacoes(db_session, sid)}
    assert set(por_lema) == {"give up", "wake up", "put on"}
    assert por_lema["give up"].pt_text == "desistiram"
    assert por_lema["give up"].extra["aligner"] == "dictionary"
    sem = por_lema["put on"]
    assert (sem.pt_start, sem.pt_end, sem.pt_text) == (None, None, None)
    assert "aligner" not in sem.extra


def test_posicoes_apontam_para_o_texto_exato_nos_dois_idiomas(db_session, annotator):
    sid = criar_historia(db_session, "TESTE-posicoes", [DESISTIR, ACORDAR, VESTIR])
    annotator.annotate_story(sid)

    segmentos = {s.id: s for s in SegmentRepository(db_session).list_by_story(sid)}
    for a in anotacoes(db_session, sid):
        seg = segmentos[a.segment_id]
        assert seg.text_en[a.en_start : a.en_end] == a.en_text
        if a.pt_start is not None:
            assert seg.text_pt[a.pt_start : a.pt_end] == a.pt_text


def test_nao_reaproveita_o_mesmo_trecho_em_portugues_na_mesma_frase(db_session, annotator):
    sid = criar_historia(
        db_session, "TESTE-repetido", [("She woke up and then she woke up again.", "Ela acordou e depois acordou de novo.")]
    )
    annotator.annotate_story(sid)
    alinhados = [(a.pt_start, a.pt_end) for a in anotacoes(db_session, sid) if a.pt_start is not None]
    assert alinhados and len(set(alinhados)) == len(alinhados)


# ---------- idempotência ----------

def test_rodar_duas_vezes_deixa_o_mesmo_numero_de_anotacoes(db_session, annotator):
    sid = criar_historia(db_session, "TESTE-idempotente", [DESISTIR, ACORDAR, VESTIR])

    primeira = annotator.annotate_story(sid)
    antes = assinatura(db_session, sid)
    segunda = annotator.annotate_story(sid)
    depois = assinatura(db_session, sid)

    assert len(antes) == len(depois) == primeira.detected == 3
    assert antes == depois  # mesmas anotações, nos mesmos lugares, sem duplicar
    assert segunda.replaced == primeira.detected


def test_reanotar_apaga_as_anotacoes_antigas(db_session, annotator):
    sid = criar_historia(db_session, "TESTE-substitui", [DESISTIR])
    segmento = SegmentRepository(db_session).list_by_story(sid)[0]
    AnnotationRepository(db_session).create(segmento, "phrasal_verb", "velha", 0, 4)

    report = annotator.annotate_story(sid)

    assert report.replaced == 1
    assert {a.lemma for a in anotacoes(db_session, sid)} == {"give up"}


# ---------- falhas ----------

def falha_na_chamada(numero: int):
    """Faz o AnnotationRepository.create falhar na chamada de número `numero`."""
    original = AnnotationRepository.create
    chamadas = [0]

    def instavel(self, *args, **kwargs):
        chamadas[0] += 1
        if chamadas[0] == numero:
            raise RuntimeError("falha simulada")
        return original(self, *args, **kwargs)

    return mock.patch.object(AnnotationRepository, "create", instavel)


def test_erro_no_meio_nao_deixa_a_historia_com_anotacoes_pela_metade(db_session, annotator):
    sid = criar_historia(db_session, "TESTE-atomico", [DESISTIR, ACORDAR, VESTIR])
    annotator.annotate_story(sid)
    antes = assinatura(db_session, sid)
    assert len(antes) == 3

    with falha_na_chamada(2), pytest.raises(RuntimeError, match="falha simulada"):
        annotator.annotate_story(sid)

    # A 1ª frase já tinha sido reanotada dentro da transação, mas tudo foi desfeito
    assert assinatura(db_session, sid) == antes


def test_historia_que_falha_nao_impede_as_outras(db_session, annotator):
    com_erro = criar_historia(db_session, "TESTE-falha", [("Please sit down.", "Por favor, sente-se.")])
    ok = criar_historia(db_session, "TESTE-ok", [DESISTIR])
    original = AnnotationRepository.create

    def instavel(self, segment, *args, **kwargs):
        # só a frase deste teste falha: o banco de desenvolvimento pode ter outras histórias com "sit down"
        if segment.text_en == "Please sit down.":
            raise RuntimeError("falha simulada")
        return original(self, segment, *args, **kwargs)

    with mock.patch.object(AnnotationRepository, "create", instavel):
        report = annotator.annotate_all()

    por_titulo = {s.title: s for s in report.stories}
    assert "falha simulada" in por_titulo["TESTE-falha"].error
    assert por_titulo["TESTE-ok"].error is None and por_titulo["TESTE-ok"].aligned == 1
    assert anotacoes(db_session, com_erro) == []
    assert len(anotacoes(db_session, ok)) == 1
    assert [s.title for s in report.failed] == ["TESTE-falha"]


def test_historia_inexistente_levanta_erro_claro(annotator):
    with pytest.raises(LookupError, match="não encontrada"):
        annotator.annotate_story(2_000_000_000)


# ---------- dry-run ----------

def test_dry_run_calcula_o_relatorio_sem_gravar(db_session, annotator):
    sid = criar_historia(db_session, "TESTE-dry", [DESISTIR, ACORDAR])

    report = annotator.annotate_story(sid, dry_run=True)

    assert (report.detected, report.aligned) == (2, 2)
    assert anotacoes(db_session, sid) == []


def test_dry_run_nao_mexe_nas_anotacoes_que_ja_existem(db_session, annotator):
    sid = criar_historia(db_session, "TESTE-dry-existente", [DESISTIR, ACORDAR])
    annotator.annotate_story(sid)
    antes = assinatura(db_session, sid)

    annotator.annotate_story(sid, dry_run=True)

    assert assinatura(db_session, sid) == antes


# ---------- as três histórias do seed ----------

def anotar_seed(db_session, annotator):
    load_seed(db_session)
    ids = {}
    for story in read_seed_files():
        ids[story.title] = StoryRepository(db_session).get_by_title(story.title).id
    reports = {titulo: annotator.annotate_story(sid) for titulo, sid in ids.items()}
    return ids, reports


def test_pelo_menos_90_por_cento_dos_phrasal_verbs_do_seed_saem_alinhados(db_session, annotator):
    _, reports = anotar_seed(db_session, annotator)
    detectados = sum(r.detected for r in reports.values())
    alinhados = sum(r.aligned for r in reports.values())
    assert detectados >= 30
    assert alinhados / detectados >= 0.9, [i for r in reports.values() for i in r.unaligned_items]


def test_alinhamento_do_seed_aponta_para_o_lugar_marcado_pela_equipe(db_session, annotator):
    ids, _ = anotar_seed(db_session, annotator)
    seed = {s.title: s for s in read_seed_files()}
    erros = []
    for titulo, sid in ids.items():
        segmentos = {s.id: s for s in SegmentRepository(db_session).list_by_story(sid)}
        for a in anotacoes(db_session, sid):
            seg = segmentos[a.segment_id]
            assert a.pt_start is not None and seg.text_pt[a.pt_start : a.pt_end] == a.pt_text
            marcado = {pv.lemma: pv.pt for pv in seed[titulo].segments[seg.position].phrasal_verbs}[a.lemma]
            if a.pt_text not in marcado and marcado not in a.pt_text:
                erros.append(f"{titulo}, frase {seg.position + 1}: {a.pt_text!r} x {marcado!r}")
    assert not erros, "\n".join(erros)


def test_anotar_o_seed_duas_vezes_nao_duplica(db_session, annotator):
    ids, _ = anotar_seed(db_session, annotator)
    antes = {t: assinatura(db_session, sid) for t, sid in ids.items()}
    for sid in ids.values():
        annotator.annotate_story(sid)
    assert {t: assinatura(db_session, sid) for t, sid in ids.items()} == antes


# ---------- o comando ----------

class SessaoDeTeste:
    """Faz o comando usar a sessão do teste (que desfaz tudo no final) e não fechá-la."""

    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


@pytest.fixture
def comando(db_session, monkeypatch):
    monkeypatch.setattr(annotate, "SessionLocal", SessaoDeTeste(db_session))
    return annotate.main


def test_comando_anota_uma_historia_e_informa_as_contagens(db_session, comando, capsys):
    sid = criar_historia(db_session, "TESTE-cli", [DESISTIR, ACORDAR, VESTIR])

    codigo = comando(["--story-id", str(sid)])

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "TESTE-cli: 3 frases, 3 trechos detectados, 2 alinhados, 1 sem alinhamento" in saida
    assert "Total: 1 histórias, 3 segmentos processados" in saida
    assert "Trechos: 3 detectados, 2 alinhados (67%), 1 sem alinhamento" in saida
    assert "Anotações substituídas: 0" in saida
    assert "'put on'" in saida  # o que ficou sem equivalente aparece no relatório
    assert len(anotacoes(db_session, sid)) == 3


def test_comando_sem_argumentos_anota_todas_as_historias(db_session, comando, capsys):
    a = criar_historia(db_session, "TESTE-cli-a", [DESISTIR])
    b = criar_historia(db_session, "TESTE-cli-b", [ACORDAR])

    codigo = comando([])

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "TESTE-cli-a: 1 frases, 1 trechos detectados, 1 alinhados" in saida
    assert "TESTE-cli-b: 1 frases, 1 trechos detectados, 1 alinhados" in saida
    assert len(anotacoes(db_session, a)) == len(anotacoes(db_session, b)) == 1


def test_comando_dry_run_avisa_e_nao_grava(db_session, comando, capsys):
    sid = criar_historia(db_session, "TESTE-cli-dry", [DESISTIR, ACORDAR])

    codigo = comando(["--story-id", str(sid), "--dry-run"])

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "[simulação, nada foi gravado]" in saida
    assert "2 trechos detectados" in saida
    assert anotacoes(db_session, sid) == []


def test_comando_com_historia_inexistente_sai_com_codigo_2(comando, capsys):
    assert comando(["--story-id", "2000000000"]) == 2
    assert "não encontrada" in capsys.readouterr().err


def test_comando_informa_falha_e_sai_com_codigo_1_sem_alterar_a_historia(db_session, comando, capsys):
    sid = criar_historia(db_session, "TESTE-cli-falha", [DESISTIR])

    with falha_na_chamada(1):
        codigo = comando(["--story-id", str(sid)])

    assert codigo == 1
    assert "nada foi alterado" in capsys.readouterr().err
    assert anotacoes(db_session, sid) == []


def test_comando_recusa_argumento_invalido():
    with pytest.raises(SystemExit) as exc:
        annotate.build_parser().parse_args(["--story-id", "abc"])
    assert exc.value.code == 2
