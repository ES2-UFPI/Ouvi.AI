"""Integridade do conteúdo do seed: não acessa o banco e não precisa de nenhum serviço externo."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.modules.stories.seed.validation import (
    MAX_SEGMENT_LENGTH,
    SEED_DIR,
    SeedError,
    check_quality,
    read_seed_files,
)

TITULOS_ESPERADOS = {"A Raposa e as Uvas", "A Lebre e a Tartaruga", "O Patinho Feio"}


# ---------- os arquivos reais ----------

def test_arquivos_reais_sao_validos_e_cobrem_as_tres_historias():
    stories = read_seed_files()
    assert {s.title for s in stories} == TITULOS_ESPERADOS


def test_frases_tem_texto_nos_dois_idiomas_e_cabem_no_limite():
    for story in read_seed_files():
        assert story.segments, story.title
        for i, seg in enumerate(story.segments):
            for texto in (seg.en, seg.pt):
                assert texto.strip() == texto and texto, f"{story.title}, frase {i + 1}: vazio ou com espaços"
                assert len(texto) <= MAX_SEGMENT_LENGTH, f"{story.title}, frase {i + 1}: texto longo demais"


def test_cada_phrasal_verb_aparece_nas_duas_frases():
    for story in read_seed_files():
        for i, seg in enumerate(story.segments):
            for pv in seg.phrasal_verbs:
                assert pv.en in seg.en, f"{story.title}, frase {i + 1}: {pv.en!r}"
                assert pv.pt in seg.pt, f"{story.title}, frase {i + 1}: {pv.pt!r}"


def test_metas_de_conteudo_da_issue():
    # de 10 a 25 frases, ao menos 6 phrasal verbs distintos e ao menos 2 separáveis por história
    assert check_quality(read_seed_files()) == []


def test_todas_as_historias_tem_origem_e_licenca_registradas():
    creditos = (SEED_DIR / "CREDITS.md").read_text(encoding="utf-8")
    for story in read_seed_files():
        assert story.source.strip()
        assert story.title in creditos, f"{story.title} não está em CREDITS.md"


# ---------- a validação recusa conteúdo ruim ----------

BASE = {
    "title": "Teste",
    "language": "en",
    "source": "domínio público",
    "segments": [
        {
            "en": "He turned off the light.",
            "pt": "Ele apagou a luz.",
            "phrasal_verbs": [{"lemma": "turn off", "en": "turned off", "pt": "apagou"}],
        }
    ],
}


def escrever(tmp_path: Path, **mudancas) -> Path:
    story = deepcopy(BASE)
    story.update(mudancas)
    (tmp_path / "historia.json").write_text(json.dumps(story), encoding="utf-8")
    return tmp_path


def problemas(tmp_path: Path, **mudancas) -> list[str]:
    with pytest.raises(SeedError) as exc:
        read_seed_files(escrever(tmp_path, **mudancas))
    return exc.value.problems


def segmento(**mudancas) -> list[dict]:
    seg = deepcopy(BASE["segments"][0])
    seg.update(mudancas)
    return [seg]


def test_base_de_teste_e_valida(tmp_path):
    assert len(read_seed_files(escrever(tmp_path))) == 1


def test_recusa_texto_vazio(tmp_path):
    assert any("'pt'" in p for p in problemas(tmp_path, segments=segmento(pt="   ")))


def test_recusa_texto_com_espacos_nas_pontas(tmp_path):
    assert any("espaços" in p for p in problemas(tmp_path, segments=segmento(en=" He turned off the light.")))


def test_recusa_texto_acima_do_limite(tmp_path):
    longo = "a" * (MAX_SEGMENT_LENGTH + 1)
    assert any("máximo" in p for p in problemas(tmp_path, segments=segmento(en=longo)))


def test_aceita_texto_exatamente_no_limite(tmp_path):
    exato = "a" * MAX_SEGMENT_LENGTH
    assert len(read_seed_files(escrever(tmp_path, segments=segmento(en=exato, phrasal_verbs=[])))) == 1


def test_recusa_idioma_invalido(tmp_path):
    assert any("language" in p for p in problemas(tmp_path, language="es"))


def test_recusa_historia_sem_frases(tmp_path):
    assert any("segments" in p for p in problemas(tmp_path, segments=[]))


def test_recusa_historia_sem_origem(tmp_path):
    assert any("source" in p for p in problemas(tmp_path, source=" "))


def test_recusa_phrasal_verb_que_nao_esta_na_frase_em_ingles(tmp_path):
    pv = [{"lemma": "turn on", "en": "turned on", "pt": "apagou"}]
    assert any("inglês" in p for p in problemas(tmp_path, segments=segmento(phrasal_verbs=pv)))


def test_recusa_equivalente_que_nao_esta_na_frase_em_portugues(tmp_path):
    pv = [{"lemma": "turn off", "en": "turned off", "pt": "desligou"}]
    assert any("português" in p for p in problemas(tmp_path, segments=segmento(phrasal_verbs=pv)))


def test_recusa_titulo_repetido_entre_arquivos(tmp_path):
    escrever(tmp_path)
    (tmp_path / "outra.json").write_text(json.dumps(BASE), encoding="utf-8")
    with pytest.raises(SeedError) as exc:
        read_seed_files(tmp_path)
    assert any("repetido" in p for p in exc.value.problems)


def test_recusa_json_quebrado(tmp_path):
    (tmp_path / "quebrado.json").write_text("{ nao e json", encoding="utf-8")
    with pytest.raises(SeedError) as exc:
        read_seed_files(tmp_path)
    assert any("quebrado.json" in p for p in exc.value.problems)


def test_recusa_pasta_sem_arquivos(tmp_path):
    with pytest.raises(SeedError):
        read_seed_files(tmp_path)


def test_lista_todos_os_problemas_de_uma_vez(tmp_path):
    ruins = problemas(tmp_path, language="es", source="", segments=segmento(pt=""))
    assert len(ruins) >= 3


# ---------- metas de conteúdo ----------

def test_meta_recusa_historia_curta_e_com_poucos_phrasal_verbs(tmp_path):
    stories = read_seed_files(escrever(tmp_path))
    ruins = check_quality(stories)
    assert any("frases" in p for p in ruins)
    assert any("phrasal verbs distintos" in p for p in ruins)
    assert any("separáveis" in p for p in ruins)


def test_meta_recusa_separavel_sem_palavra_entre_verbo_e_particula(tmp_path):
    pv = [{"lemma": "turn off", "en": "turned off", "pt": "apagou", "separable": True}]
    stories = read_seed_files(escrever(tmp_path, segments=segmento(phrasal_verbs=pv)))
    assert any("não tem palavra entre" in p for p in check_quality(stories))
