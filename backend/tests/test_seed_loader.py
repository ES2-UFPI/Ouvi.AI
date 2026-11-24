"""Testes do carregador do seed (`load_seed`): grava as histórias dos JSON no banco sem duplicar nada.

Escritos para travar o comportamento ANTES de refatorar a função (que era longa demais): criar, repetir, atualizar
o texto, frases a mais no banco (aviso e `prune`), simulação (`dry_run`), idioma e atomicidade. Usam um diretório de
seed temporário e a transação de teste (desfeita no fim): os dados do ambiente de desenvolvimento não são tocados.
"""
import json
from pathlib import Path

import pytest

from app.modules.stories.models import Story
from app.modules.stories.repository import AnnotationRepository, SegmentRepository, StoryRepository
from app.modules.stories.seed.loader import SeedReport, load_seed
from app.modules.stories.seed.validation import SeedError

TITULO = "História do carregador XYZ"
FRASES = [
    ("One day a fox slept.", "Um dia uma raposa dormiu."),
    ("She woke up early.", "Ela acordou cedo."),
    ("The end came soon.", "O fim chegou logo."),
]


def escrever(pasta: Path, frases=FRASES, titulo: str = TITULO, language: str = "en", description: str | None = "Resumo") -> Path:
    historia = {
        "title": titulo,
        "language": language,
        "description": description,
        "source": "domínio público",
        "segments": [{"en": en, "pt": pt, "phrasal_verbs": []} for en, pt in frases],
    }
    (pasta / "historia.json").write_text(json.dumps(historia), encoding="utf-8")
    return pasta


def frases_do_banco(db, titulo: str = TITULO) -> list[tuple[int, str, str]]:
    historia = StoryRepository(db).get_by_title(titulo)
    return [(s.position, s.text_en, s.text_pt) for s in SegmentRepository(db).list_by_story(historia.id)]


# ---------- criar e repetir ----------

def test_cria_a_historia_e_as_frases_na_ordem_do_arquivo(db_session, tmp_path):
    relatorio = load_seed(db_session, escrever(tmp_path))

    assert (relatorio.stories_created, relatorio.stories_found) == (1, 0)
    assert (relatorio.segments_created, relatorio.segments_updated, relatorio.segments_unchanged) == (3, 0, 0)
    assert frases_do_banco(db_session) == [(i, en, pt) for i, (en, pt) in enumerate(FRASES)]
    historia = StoryRepository(db_session).get_by_title(TITULO)
    assert (historia.language, historia.description) == ("en", "Resumo")


def test_repetir_nao_duplica_nada(db_session, tmp_path):
    pasta = escrever(tmp_path)
    load_seed(db_session, pasta)

    segunda = load_seed(db_session, pasta)

    assert (segunda.stories_created, segunda.stories_found) == (0, 1)
    assert (segunda.segments_created, segunda.segments_updated, segunda.segments_unchanged) == (0, 0, 3)
    assert len(frases_do_banco(db_session)) == 3
    assert db_session.query(Story).filter(Story.title == TITULO).count() == 1


def test_frase_nova_no_fim_do_arquivo_e_criada(db_session, tmp_path):
    load_seed(db_session, escrever(tmp_path))

    relatorio = load_seed(db_session, escrever(tmp_path, FRASES + [("It was over.", "Acabou.")]))

    assert (relatorio.segments_created, relatorio.segments_unchanged) == (1, 3)
    assert frases_do_banco(db_session)[-1] == (3, "It was over.", "Acabou.")


# ---------- texto alterado ----------

def test_texto_alterado_atualiza_a_frase_e_apaga_as_anotacoes_dela(db_session, tmp_path):
    load_seed(db_session, escrever(tmp_path))
    historia = StoryRepository(db_session).get_by_title(TITULO)
    frase = SegmentRepository(db_session).list_by_story(historia.id)[1]
    AnnotationRepository(db_session).create(frase, "phrasal_verb", "wake up", 4, 11, 4, 11)
    AnnotationRepository(db_session).create(frase, "difficult_word", "early", 12, 17, 12, 16)
    outras = [(en, pt) for en, pt in FRASES]
    outras[1] = ("She woke up late.", "Ela acordou tarde.")

    relatorio = load_seed(db_session, escrever(tmp_path, outras))

    assert (relatorio.segments_updated, relatorio.segments_unchanged) == (1, 2)
    assert relatorio.annotations_cleared == 2  # as posições antigas deixaram de valer
    assert frases_do_banco(db_session)[1] == (1, "She woke up late.", "Ela acordou tarde.")
    db_session.expire_all()
    assert AnnotationRepository(db_session).list_by_segment(frase.id) == []


def test_frase_igual_nao_perde_as_anotacoes(db_session, tmp_path):
    pasta = escrever(tmp_path)
    load_seed(db_session, pasta)
    historia = StoryRepository(db_session).get_by_title(TITULO)
    frase = SegmentRepository(db_session).list_by_story(historia.id)[1]
    AnnotationRepository(db_session).create(frase, "phrasal_verb", "wake up", 4, 11, 4, 11)

    relatorio = load_seed(db_session, pasta)

    assert relatorio.annotations_cleared == 0
    assert len(AnnotationRepository(db_session).list_by_segment(frase.id)) == 1


def test_idioma_da_historia_e_atualizado(db_session, tmp_path):
    load_seed(db_session, escrever(tmp_path))

    load_seed(db_session, escrever(tmp_path, language="pt"))

    assert StoryRepository(db_session).get_by_title(TITULO).language == "pt"


# ---------- frases a mais no banco ----------

def test_frases_alem_do_fim_do_arquivo_viram_aviso_sem_prune(db_session, tmp_path):
    load_seed(db_session, escrever(tmp_path))

    relatorio = load_seed(db_session, escrever(tmp_path, FRASES[:1]))

    assert relatorio.segments_pruned == 0
    assert len(relatorio.warnings) == 1
    assert TITULO in relatorio.warnings[0] and "2 frase(s)" in relatorio.warnings[0] and "--prune" in relatorio.warnings[0]
    assert len(frases_do_banco(db_session)) == 3  # nada foi apagado


def test_prune_apaga_as_frases_alem_do_fim_do_arquivo(db_session, tmp_path):
    load_seed(db_session, escrever(tmp_path))

    relatorio = load_seed(db_session, escrever(tmp_path, FRASES[:1]), prune=True)

    assert relatorio.segments_pruned == 2 and relatorio.warnings == []
    assert frases_do_banco(db_session) == [(0, *FRASES[0])]


# ---------- simulação, validação e atomicidade ----------

def test_dry_run_calcula_o_relatorio_sem_gravar_nada(db_session, tmp_path):
    relatorio = load_seed(db_session, escrever(tmp_path), dry_run=True)

    assert (relatorio.stories_created, relatorio.segments_created) == (1, 3)
    assert StoryRepository(db_session).get_by_title(TITULO) is None


def test_dry_run_nao_altera_o_que_ja_existe(db_session, tmp_path):
    load_seed(db_session, escrever(tmp_path))
    mudadas = [("Changed.", "Mudou.")] + FRASES[1:]

    relatorio = load_seed(db_session, escrever(tmp_path, mudadas), dry_run=True)

    assert relatorio.segments_updated == 1
    assert frases_do_banco(db_session)[0] == (0, *FRASES[0])  # o texto antigo continua


def test_arquivo_invalido_levanta_erro_antes_de_tocar_no_banco(db_session, tmp_path):
    (tmp_path / "ruim.json").write_text(json.dumps({"title": TITULO}), encoding="utf-8")

    with pytest.raises(SeedError):
        load_seed(db_session, tmp_path)

    assert StoryRepository(db_session).get_by_title(TITULO) is None


def test_falha_no_meio_desfaz_tudo_e_repassa_o_erro(db_session, tmp_path, monkeypatch):
    original = SegmentRepository.create
    chamadas = {"n": 0}

    def quebra_na_segunda(self, *args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise RuntimeError("falha simulada")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SegmentRepository, "create", quebra_na_segunda)

    with pytest.raises(RuntimeError, match="falha simulada"):
        load_seed(db_session, escrever(tmp_path))

    assert StoryRepository(db_session).get_by_title(TITULO) is None  # nem a história nem a 1ª frase ficaram


def test_o_relatorio_comeca_zerado():
    assert SeedReport() == SeedReport(0, 0, 0, 0, 0, 0, 0, [])
