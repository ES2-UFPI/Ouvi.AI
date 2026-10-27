"""Testes do alinhamento PT/EN e do dicionário de equivalentes. Não usam banco nem spaCy."""
import json

import pytest

from app.modules.stories.models import KIND_PHRASAL_VERB
from app.modules.stories.nlp.alignment import (
    DictionaryAligner,
    EquivalentsFileError,
    load_pt_equivalents,
)
from app.modules.stories.nlp.base import DetectedSpan
from app.modules.stories.seed.validation import read_seed_files


def span(lemma: str, text_en: str, trecho: str, occurrence: int = 1) -> DetectedSpan:
    """Cria o trecho detectado na n-ésima ocorrência de `trecho` dentro de `text_en`."""
    start = -1
    for _ in range(occurrence):
        start = text_en.index(trecho, start + 1)
    return DetectedSpan(KIND_PHRASAL_VERB, lemma, start, start + len(trecho), trecho)


def align(forms: list[str], text_en: str, trecho: str, text_pt: str, occurrence: int = 1, taken=()):
    aligner = DictionaryAligner({"give up": forms})
    return aligner.align(span("give up", text_en, trecho, occurrence), text_en, text_pt, taken)


def recorte(text: str, result: tuple[int, int] | None) -> str | None:
    return None if result is None else text[result[0] : result[1]]


# ---------- busca ----------

def test_ignora_maiusculas_e_acentos():
    pt = "ELES SAÍRAM cedo."
    assert recorte(pt, align(["sairam"], "They left early.", "left", pt)) == "SAÍRAM"


def test_forma_com_acento_casa_com_texto_sem_acento():
    pt = "Eles sairam cedo."
    assert recorte(pt, align(["saíram"], "They left early.", "left", pt)) == "sairam"


def test_posicoes_valem_para_o_texto_original_mesmo_com_acentos_antes():
    pt = "Até àquela hora, ação alguma: ele desistiu."
    resultado = align(["desistiu"], "He gave up.", "gave up", pt)
    assert recorte(pt, resultado) == "desistiu"


def test_respeita_limite_de_palavra():
    pt = "Nós vamos sairemos cedo."
    assert align(["sair"], "We leave.", "leave", pt) is None
    assert recorte("Quero sair, agora.", align(["sair"], "I leave.", "leave", "Quero sair, agora.")) == "sair"


def test_forma_com_hifen_e_clitico():
    pt = "Por fim, sentou-se debaixo da árvore."
    assert recorte(pt, align(["sentou-se"], "She sat down.", "sat down", pt)) == "sentou-se"


def test_com_varias_formas_no_mesmo_lugar_fica_a_mais_longa():
    pt = "Por fim, sentou-se debaixo da árvore."
    assert recorte(pt, align(["sentou", "sentou-se"], "She sat down.", "sat down", pt)) == "sentou-se"


def test_aceita_espacos_diferentes_dentro_da_forma():
    pt = "Ele  pegou   no sono."
    assert recorte(pt, align(["pegou no sono"], "He dozed off.", "dozed off", pt)) == "pegou   no sono"


# ---------- escolha entre ocorrências ----------

PT_DUAS = "Ela desistiu cedo e depois desistiu de novo."
EN_DUAS = "She gave up early and then gave up again."


def test_escolhe_a_ocorrencia_mais_proxima_da_posicao_relativa_no_ingles():
    primeira = align(["desistiu"], EN_DUAS, "gave up", PT_DUAS, occurrence=1)
    segunda = align(["desistiu"], EN_DUAS, "gave up", PT_DUAS, occurrence=2)
    inicio_1 = PT_DUAS.index("desistiu")
    inicio_2 = PT_DUAS.index("desistiu", inicio_1 + 1)
    assert primeira == (inicio_1, inicio_1 + len("desistiu"))
    assert segunda == (inicio_2, inicio_2 + len("desistiu"))
    assert primeira != segunda


def test_nao_reaproveita_trecho_ja_usado_por_outra_anotacao():
    primeira = align(["desistiu"], EN_DUAS, "gave up", PT_DUAS, occurrence=1)
    # a segunda anotação pede o mesmo lugar, mas ele já foi tomado: fica com a outra ocorrência
    outra = align(["desistiu"], EN_DUAS, "gave up", PT_DUAS, occurrence=1, taken=[primeira])
    assert outra is not None and outra != primeira


def test_devolve_none_se_todas_as_ocorrencias_ja_foram_usadas():
    pt = "Ela desistiu."
    usado = align(["desistiu"], "She gave up.", "gave up", pt)
    assert align(["desistiu"], "She gave up.", "gave up", pt, taken=[usado]) is None


# ---------- curinga ----------

def test_curinga_aceita_de_uma_a_quatro_palavras_no_meio():
    forms = ["deixou ... para trás"]
    en, trecho = "He left the tortoise behind.", "left the tortoise behind"
    for pt in ("Ele deixou a tartaruga para trás.", "Ele deixou o velho amigo cansado para trás.", "Ele deixou tudo para trás."):
        achou = align(forms, en, trecho, pt)
        assert achou is not None and pt[achou[0] : achou[1]].startswith("deixou") and pt[achou[0] : achou[1]].endswith("para trás")


def test_curinga_recusa_zero_palavras_e_mais_de_quatro():
    forms = ["deixou ... para trás"]
    en, trecho = "He left the tortoise behind.", "left the tortoise behind"
    assert align(forms, en, trecho, "Ele deixou para trás a tartaruga.") is None
    assert align(forms, en, trecho, "Ele deixou o velho amigo de infância tão cansado para trás.") is None


# ---------- sem equivalente ----------

def test_devolve_none_quando_nenhuma_forma_aparece():
    assert align(["desistiu"], "She gave up.", "gave up", "Ela continuou tentando.") is None


def test_devolve_none_para_lema_fora_do_dicionario():
    aligner = DictionaryAligner({"give up": ["desistiu"]})
    texto = "He turned off the light."
    assert aligner.align(span("turn off", texto, "turned off"), texto, "Ele desligou a luz.") is None


def test_devolve_none_para_texto_em_portugues_vazio():
    assert align(["desistiu"], "She gave up.", "gave up", "") is None


# ---------- arquivo de equivalentes ----------

def test_arquivo_de_equivalentes_e_valido():
    equivalentes = load_pt_equivalents()
    assert len(equivalentes) >= 30
    for lema, formas in equivalentes.items():
        assert formas, lema


def test_lemas_do_dicionario_existem_na_lista_de_phrasal_verbs_aceitos():
    # um lema que o detector nunca acha nunca seria consultado
    from app.modules.stories.nlp.phrasal_verbs import load_accepted_phrasal_verbs

    assert set(load_pt_equivalents()) - load_accepted_phrasal_verbs() == set()


def test_dicionario_cobre_todos_os_phrasal_verbs_do_seed():
    do_seed = {pv.lemma for s in read_seed_files() for seg in s.segments for pv in seg.phrasal_verbs}
    assert do_seed - set(load_pt_equivalents()) == set()


def test_cada_equivalente_marcado_no_seed_e_encontrado_no_lugar_certo():
    """Para cada phrasal verb do seed, o alinhador acha um trecho que se sobrepõe ao equivalente
    marcado pela equipe, e pelo menos 90% dos casos são encontrados (meta da issue)."""
    aligner = DictionaryAligner()
    total = achados = 0
    erros = []
    for story in read_seed_files():
        for numero, seg in enumerate(story.segments, 1):
            for pv in seg.phrasal_verbs:
                total += 1
                resultado = aligner.align(span(pv.lemma, seg.en, pv.en), seg.en, seg.pt)
                if resultado is None:
                    erros.append(f"{story.title}, frase {numero}: {pv.lemma!r} não alinhado")
                    continue
                achados += 1
                trecho = seg.pt[resultado[0] : resultado[1]]
                if trecho not in pv.pt and pv.pt not in trecho:
                    erros.append(f"{story.title}, frase {numero}: {trecho!r} não bate com {pv.pt!r}")
    assert not erros, "\n".join(erros)
    assert achados / total >= 0.9


def test_validacao_do_arquivo_lista_todos_os_problemas(tmp_path):
    ruim = tmp_path / "ruim.json"
    ruim.write_text(
        json.dumps(
            {
                "Turn Off": ["desligar"],  # maiúsculas
                "give": ["dar"],  # só uma palavra
                "give up": [],  # sem formas
                "set out": ["... partiu", "partiu", "partiu"],  # curinga no início e repetida
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EquivalentsFileError) as exc:
        load_pt_equivalents(ruim)
    mensagem = str(exc.value)
    for pedaco in ("Turn Off", "'give'", "'give up'", "começar nem terminar", "repetida"):
        assert pedaco in mensagem, pedaco
