"""Testes do dicionário de palavras difíceis (#103) e da anotação por tipo sem sobreposição (#104).

Os de anotação rodam no banco, numa transação desfeita no final (veja `db_session` no conftest).
"""
import json
import unicodedata

import pytest
from sqlalchemy import select

from app.modules.stories import annotate
from app.modules.stories.annotator import KindStats, TextAnnotator
from app.modules.stories.models import KIND_DIFFICULT_WORD, KIND_PHRASAL_VERB, Annotation, Segment
from app.modules.stories.nlp.alignment import (
    DictionaryAligner,
    EquivalentsFileError,
    load_all_equivalents,
    load_pt_equivalents,
    load_pt_words,
)
from app.modules.stories.nlp.base import DetectedSpan
from app.modules.stories.nlp.difficult_words import DifficultWordDetector
from app.modules.stories.repository import AnnotationRepository, SegmentRepository, StoryRepository
from app.modules.stories.seed.validation import read_seed_files

# (inglês, português). "dozed off" é phrasal verb; "dozed" sozinho seria palavra difícil.
COCHILO = ("The hare dozed off under the tree.", "A lebre cochilou debaixo da árvore.")
TARTARUGA = ("The tortoise gave up at noon.", "A tartaruga desistiu ao meio-dia.")


def criar_historia(db, titulo, frases):
    story = StoryRepository(db).create(titulo, None, "en")
    for posicao, (en, pt) in enumerate(frases):
        SegmentRepository(db).create(story.id, posicao, en, pt)
    return story.id


def anotacoes(db, story_id, kind=None):
    db.expire_all()
    stmt = (
        select(Annotation)
        .join(Segment, Segment.id == Annotation.segment_id)
        .where(Segment.story_id == story_id)
        .order_by(Segment.position, Annotation.en_start)
    )
    if kind:
        stmt = stmt.where(Annotation.kind == kind)
    return list(db.scalars(stmt))


def assinatura(db, story_id, kind=None):
    return [(a.kind, a.lemma, a.en_start, a.en_end, a.pt_start, a.pt_end) for a in anotacoes(db, story_id, kind)]


def _fold(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if not unicodedata.combining(c))


# ---------- dicionário (#103) ----------

def test_dicionario_de_palavras_e_valido_e_nao_colide_com_o_de_phrasal_verbs():
    palavras = load_pt_words()
    assert len(palavras) >= 15
    assert all(" " not in lemma for lemma in palavras)
    assert not set(palavras) & set(load_pt_equivalents())
    assert set(load_all_equivalents()) == set(palavras) | set(load_pt_equivalents())


def test_validador_lista_todos_os_problemas_de_uma_vez(tmp_path):
    arquivo = tmp_path / "pt_words.json"
    arquivo.write_text(json.dumps({"Tortoise": ["tartaruga"], "give up": ["desistir"], "hare": []}), encoding="utf-8")
    with pytest.raises(EquivalentsFileError) as exc:
        load_pt_words(arquivo)
    mensagem = str(exc.value)
    assert "'Tortoise'" in mensagem and "'give up'" in mensagem and "'hare'" in mensagem
    assert "uma única palavra" in mensagem


def test_lema_de_duas_palavras_no_dicionario_de_palavras_e_erro(tmp_path):
    phrasal = tmp_path / "pv.json"
    phrasal.write_text(json.dumps({"give up": ["desistiu"]}), encoding="utf-8")
    palavras = tmp_path / "w.json"
    palavras.write_text(json.dumps({"give up": ["desistiu"]}), encoding="utf-8")
    load_pt_words.cache_clear()  # o arquivo de palavras inválido acima não pode ficar no cache
    with pytest.raises(EquivalentsFileError):
        # a validação por número de palavras já impede que uma chave apareça nos dois arquivos
        load_all_equivalents(phrasal, palavras)


def test_junta_dicionarios_validos(tmp_path):
    phrasal = tmp_path / "pv.json"
    phrasal.write_text(json.dumps({"give up": ["desistiu"]}), encoding="utf-8")
    palavras = tmp_path / "w.json"
    palavras.write_text(json.dumps({"tortoise": ["tartaruga"]}), encoding="utf-8")
    assert "tortoise" in load_all_equivalents(phrasal, palavras)


def test_palavras_do_seed_alinham_no_lugar_certo():
    """Cada palavra difícil detectada e alinhada no seed tem o português no lugar certo, e a forma achada
    é uma das formas do dicionário para aquele lema."""
    detector, aligner, palavras = DifficultWordDetector(), DictionaryAligner(), load_pt_words()
    alinhadas_por_historia = {}
    for story in read_seed_files():
        alinhadas = 0
        for seg in story.segments:
            taken = []
            for span in detector.detect(seg.en):
                achado = aligner.align(span, seg.en, seg.pt, taken)
                if achado is None:
                    continue
                taken.append(achado)
                trecho = seg.pt[achado[0] : achado[1]]
                assert _fold(trecho) in {_fold(f) for f in palavras[span.lemma]}, (story.title, span.lemma, trecho)
                alinhadas += 1
        alinhadas_por_historia[story.title] = alinhadas
    # Meta da issue: 15 por história. A Raposa e as Uvas tem só 12 frases curtas e fica abaixo (veja o README).
    assert sum(alinhadas_por_historia.values()) >= 35, alinhadas_por_historia
    assert all(n >= 8 for n in alinhadas_por_historia.values()), alinhadas_por_historia


@pytest.mark.parametrize("en, pt, lema, esperado", [
    ("The tortoise won.", "A tartaruga venceu.", "tortoise", "tartaruga"),
    ("The grapes were sour.", "As uvas estavam azedas.", "sour", "azedas"),
    ("A hare was always bragging.", "Uma lebre vivia se gabando.", "brag", "se gabando"),
])
def test_alinhamento_de_palavras_conhecidas(en, pt, lema, esperado):
    span = next(s for s in DifficultWordDetector().detect(en) if s.lemma == lema)
    inicio, fim = DictionaryAligner().align(span, en, pt)
    assert pt[inicio:fim] == esperado


# ---------- anotação por tipo (#104) ----------

def anotador(db, *kinds):
    return TextAnnotator.with_defaults(db, list(kinds) or None)


def test_sem_kind_anota_todos_os_tipos(db_session):
    sid = criar_historia(db_session, "TESTE-us10-todos", [TARTARUGA])
    report = anotador(db_session).annotate_story(sid)
    tipos = {a.kind for a in anotacoes(db_session, sid)}
    assert tipos == {KIND_PHRASAL_VERB, KIND_DIFFICULT_WORD}
    assert report.by_kind[KIND_PHRASAL_VERB].detected == 1
    assert report.by_kind[KIND_DIFFICULT_WORD].detected == 1


def test_anotar_palavras_dificeis_nao_mexe_nos_phrasal_verbs_e_vice_versa(db_session):
    sid = criar_historia(db_session, "TESTE-us10-isolamento", [TARTARUGA, COCHILO])
    anotador(db_session, KIND_PHRASAL_VERB).annotate_story(sid)
    phrasal_antes = assinatura(db_session, sid, KIND_PHRASAL_VERB)
    assert phrasal_antes

    report = anotador(db_session, KIND_DIFFICULT_WORD).annotate_story(sid)
    assert assinatura(db_session, sid, KIND_PHRASAL_VERB) == phrasal_antes
    assert report.replaced == 0  # nenhum phrasal verb foi apagado
    palavras_antes = assinatura(db_session, sid, KIND_DIFFICULT_WORD)
    assert palavras_antes

    anotador(db_session, KIND_PHRASAL_VERB).annotate_story(sid)
    assert assinatura(db_session, sid, KIND_DIFFICULT_WORD) == palavras_antes
    assert assinatura(db_session, sid, KIND_PHRASAL_VERB) == phrasal_antes


def test_rodar_duas_vezes_mantem_o_numero_de_cada_tipo(db_session):
    sid = criar_historia(db_session, "TESTE-us10-idempotente", [TARTARUGA, COCHILO])
    for kinds in [(), (KIND_DIFFICULT_WORD,), (KIND_PHRASAL_VERB,)]:
        anotador(db_session, *kinds).annotate_story(sid)
        antes = assinatura(db_session, sid)
        anotador(db_session, *kinds).annotate_story(sid)
        assert assinatura(db_session, sid) == antes


def test_palavra_dentro_de_phrasal_verb_nao_vira_palavra_dificil(db_session):
    sid = criar_historia(db_session, "TESTE-us10-sobreposicao", [COCHILO])
    report = anotador(db_session).annotate_story(sid)

    lemas = {(a.kind, a.lemma) for a in anotacoes(db_session, sid)}
    assert (KIND_PHRASAL_VERB, "doze off") in lemas
    assert (KIND_DIFFICULT_WORD, "doze") not in lemas
    assert (KIND_DIFFICULT_WORD, "hare") in lemas
    assert report.by_kind[KIND_DIFFICULT_WORD].discarded == 1


def test_phrasal_verb_novo_tira_o_lugar_da_palavra_dificil_ja_gravada(db_session):
    sid = criar_historia(db_session, "TESTE-us10-prioridade", [COCHILO])
    segmento = SegmentRepository(db_session).list_by_story(sid)[0]
    # palavra difícil gravada antes, por exemplo por uma anotação feita só desse tipo
    AnnotationRepository(db_session).create(segmento, KIND_DIFFICULT_WORD, "doze", 9, 14)

    report = anotador(db_session, KIND_PHRASAL_VERB).annotate_story(sid)

    assert (KIND_DIFFICULT_WORD, "doze") not in {(a.kind, a.lemma) for a in anotacoes(db_session, sid)}
    assert report.by_kind[KIND_DIFFICULT_WORD].discarded == 1


class _Fixo:
    """Detector falso: devolve sempre os mesmos trechos."""

    def __init__(self, kind, *trechos):
        self.kind = kind
        self.trechos = trechos

    def detect(self, text):
        return [DetectedSpan(self.kind, lemma, s, e, text[s:e]) for lemma, s, e in self.trechos]


class _SemAlinhamento:
    name = "nenhum"

    def align(self, span, text_en, text_pt, taken=()):
        return None


def test_mesmo_tipo_sobreposto_fica_o_primeiro(db_session):
    sid = criar_historia(db_session, "TESTE-us10-mesmo-tipo", [("abcdef ghi", "x")])
    detector = _Fixo(KIND_DIFFICULT_WORD, ("abc", 0, 3), ("bcd", 1, 4), ("ghi", 7, 10))
    report = TextAnnotator(db_session, [detector], _SemAlinhamento()).annotate_story(sid)
    assert [a.lemma for a in anotacoes(db_session, sid)] == ["abc", "ghi"]
    assert report.by_kind[KIND_DIFFICULT_WORD] == KindStats(detected=2, aligned=0, discarded=1)


def test_dry_run_nao_grava_nada(db_session):
    sid = criar_historia(db_session, "TESTE-us10-dry", [TARTARUGA])
    anotador(db_session).annotate_story(sid, dry_run=True)
    assert anotacoes(db_session, sid) == []


# ---------- comando ----------

class _Sessao:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


def test_comando_com_kind_anota_so_aquele_tipo_e_mostra_o_relatorio_por_tipo(db_session, monkeypatch, capsys):
    monkeypatch.setattr(annotate, "SessionLocal", _Sessao(db_session))
    sid = criar_historia(db_session, "TESTE-us10-cli", [TARTARUGA, COCHILO])

    assert annotate.main(["--story-id", str(sid), "--kind", KIND_DIFFICULT_WORD]) == 0

    saida = capsys.readouterr().out
    assert "Por tipo:" in saida
    assert f"{KIND_DIFFICULT_WORD}: " in saida and f"{KIND_PHRASAL_VERB}: " not in saida
    assert {a.kind for a in anotacoes(db_session, sid)} == {KIND_DIFFICULT_WORD}


def test_comando_recusa_tipo_desconhecido():
    with pytest.raises(SystemExit):
        annotate.build_parser().parse_args(["--kind", "idiom"])
