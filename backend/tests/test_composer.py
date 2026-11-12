"""Testes do AudioComposer, das estratégias de troca e da densidade (#82).

Escritos antes do código (TDD). A maior parte usa anotações e frases simuladas (sem banco, sem spaCy e
sem rede); o último bloco usa as histórias reais do seed, no banco de teste (transação desfeita no final).
"""
import random
from dataclasses import dataclass, field
from xml.etree import ElementTree

import pytest

from app.integrations.tts import FakeTTSProvider
from app.modules.audio.composer import (
    DENSITY_SHARE,
    AudioComposer,
    ComposedText,
    PhrasalVerbStrategy,
    Swap,
    SwapStrategyFactory,
    UnknownSwapStrategyError,
)

KIND = "phrasal_verb"


@dataclass
class Anot:
    """Anotação simulada: só os campos que o compositor lê."""

    id: int
    kind: str = KIND
    pt_start: int | None = None
    pt_end: int | None = None
    pt_text: str | None = None
    en_start: int = 0
    en_end: int = 1
    en_text: str = ""


@dataclass
class Frase:
    """Frase simulada (um Segment)."""

    text_pt: str
    text_en: str
    id: int = 1
    position: int = 0
    annotations: list = field(default_factory=list)


def anot(id: int, frase: Frase, trecho_pt: str, trecho_en: str, kind: str = KIND) -> Anot:
    """Anotação com as posições calculadas a partir da frase, como o anotador faz."""
    ps, es = frase.text_pt.index(trecho_pt), frase.text_en.index(trecho_en)
    return Anot(id, kind, ps, ps + len(trecho_pt), trecho_pt, es, es + len(trecho_en), trecho_en)


def sem_equivalente(id: int, frase: Frase, trecho_en: str) -> Anot:
    es = frase.text_en.index(trecho_en)
    return Anot(id, KIND, None, None, None, es, es + len(trecho_en), trecho_en)


def xml(ssml: str) -> ElementTree.Element:
    return ElementTree.fromstring(ssml)  # levanta ParseError se o SSML não for XML válido


def texto_falado(ssml: str) -> str:
    return "".join(xml(ssml).itertext())


composer = AudioComposer()

LUZ = Frase("A raposa desistiu das uvas.", "The fox gave up on the grapes.")
LUZ.annotations = [anot(1, LUZ, "desistiu", "gave up")]


# ---------- composição ----------

def test_frase_sem_trechos_selecionados_vira_ssml_simples_sem_lang():
    resultado = composer.compose(LUZ, set(), "pt")

    assert resultado.ssml == '<speak version="1.0" xml:lang="pt-BR">A raposa desistiu das uvas.</speak>'
    assert resultado.text == "A raposa desistiu das uvas."
    assert resultado.swaps == []
    assert "<lang" not in resultado.ssml


def test_trecho_selecionado_e_substituido_por_lang_em_ingles():
    resultado = composer.compose(LUZ, {1}, "pt")

    assert resultado.ssml == (
        '<speak version="1.0" xml:lang="pt-BR">A raposa <lang xml:lang="en-US">gave up</lang> das uvas.</speak>'
    )
    assert resultado.swaps == [Swap(start=9, end=17, text="desistiu", spoken="gave up", lang="en-US", annotation_id=1)]


def test_o_texto_exibido_e_sempre_o_texto_base_original():
    resultado = composer.compose(LUZ, {1}, "pt")
    assert resultado.text == LUZ.text_pt  # a tela mostra o português, mesmo com a troca falada em inglês


def test_posicao_do_swap_corresponde_ao_texto_trocado():
    resultado = composer.compose(LUZ, {1}, "pt")
    for swap in resultado.swaps:
        assert resultado.text[swap.start : swap.end] == swap.text


def test_so_as_anotacoes_selecionadas_sao_trocadas():
    frase = Frase("Ele acordou cedo e desistiu depois.", "He woke up early and gave up later.")
    frase.annotations = [anot(1, frase, "acordou", "woke up"), anot(2, frase, "desistiu", "gave up")]

    resultado = composer.compose(frase, {2}, "pt")

    assert [s.annotation_id for s in resultado.swaps] == [2]
    assert "acordou" in texto_falado(resultado.ssml)
    assert resultado.ssml.count("<lang") == 1


def test_varios_trechos_na_mesma_frase_nao_corrompem_as_posicoes():
    frase = Frase("Ele acordou cedo e desistiu depois.", "He woke up early and gave up later.")
    frase.annotations = [anot(1, frase, "acordou", "woke up"), anot(2, frase, "desistiu", "gave up")]

    resultado = composer.compose(frase, {1, 2}, "pt")

    assert texto_falado(resultado.ssml) == "Ele woke up cedo e gave up depois."
    assert [(s.text, s.spoken) for s in resultado.swaps] == [("acordou", "woke up"), ("desistiu", "gave up")]
    for swap in resultado.swaps:
        assert frase.text_pt[swap.start : swap.end] == swap.text


def test_os_swaps_saem_em_ordem_de_posicao_mesmo_com_as_anotacoes_fora_de_ordem():
    frase = Frase("Ele acordou cedo e desistiu depois.", "He woke up early and gave up later.")
    frase.annotations = [anot(2, frase, "desistiu", "gave up"), anot(1, frase, "acordou", "woke up")]

    resultado = composer.compose(frase, {1, 2}, "pt")

    assert [s.start for s in resultado.swaps] == sorted(s.start for s in resultado.swaps)
    assert texto_falado(resultado.ssml) == "Ele woke up cedo e gave up depois."


def test_trecho_no_comeco_e_no_fim_da_frase():
    frase = Frase("Desistiu cedo e acordou", "He gave up early and woke up")
    frase.annotations = [anot(1, frase, "Desistiu", "gave up"), anot(2, frase, "acordou", "woke up")]
    resultado = composer.compose(frase, {1, 2}, "pt")
    assert texto_falado(resultado.ssml) == "gave up cedo e woke up"


def test_duas_anotacoes_que_se_sobrepoem_mantem_a_primeira():
    frase = Frase("Ele decidiu desistir logo.", "He decided to give up soon.")
    frase.annotations = [
        anot(1, frase, "decidiu desistir", "decided to give up"),
        anot(2, frase, "desistir logo", "give up soon"),
    ]

    resultado = composer.compose(frase, {1, 2}, "pt")

    assert [s.annotation_id for s in resultado.swaps] == [1]
    assert texto_falado(resultado.ssml) == "Ele decided to give up logo."


def test_anotacao_sem_equivalente_em_portugues_nunca_e_trocada():
    frase = Frase("Ele vestiu o casaco.", "He put on his coat.")
    frase.annotations = [sem_equivalente(7, frase, "put on")]

    resultado = composer.compose(frase, {7}, "pt")

    assert resultado.swaps == [] and "<lang" not in resultado.ssml


def test_o_id_selecionado_que_nao_existe_na_frase_e_ignorado():
    assert composer.compose(LUZ, {999}, "pt").swaps == []


def test_anotacao_desatualizada_em_relacao_ao_texto_levanta_erro_claro():
    frase = Frase("A raposa desistiu das uvas.", "The fox gave up on the grapes.")
    errada = Anot(1, KIND, 0, 8, "desistiu", 0, 1, "gave up")  # as posições 0 a 8 são "A raposa"
    frase.annotations = [errada]

    with pytest.raises(ValueError, match="posições"):
        composer.compose(frase, {1}, "pt")


# ---------- escape de caracteres especiais ----------

TEXTO_ESPECIAL = 'Tom & Jerry disseram "oi" <rápido>: não desistiu d\'uma vez!'


def test_caracteres_especiais_nao_quebram_o_ssml():
    frase = Frase(TEXTO_ESPECIAL, "Tom and Jerry said hi: he gave up & left")
    frase.annotations = [anot(1, frase, "desistiu", "gave up & left")]

    resultado = composer.compose(frase, {1}, "pt")

    raiz = xml(resultado.ssml)  # XML válido
    assert raiz.tag == "speak"
    assert texto_falado(resultado.ssml) == TEXTO_ESPECIAL.replace("desistiu", "gave up & left")


def test_o_texto_comum_e_escapado_sem_tocar_nas_tags():
    frase = Frase('Tom & Jerry disseram "oi" <rápido>', "x")
    resultado = composer.compose(frase, set(), "pt")
    assert "Tom &amp; Jerry disseram &quot;oi&quot; &lt;rápido&gt;" in resultado.ssml
    assert resultado.text == 'Tom & Jerry disseram "oi" <rápido>'  # o texto exibido continua sem escape


def test_o_trecho_falado_tambem_e_escapado():
    frase = Frase("Ele desistiu.", "He gave up.")
    ann = anot(1, frase, "desistiu", "gave up")
    ann.en_text = "gave <up> & \"leave\""
    frase.annotations = [ann]
    resultado = composer.compose(frase, {1}, "pt")
    assert xml(resultado.ssml).find("lang").text == 'gave <up> & "leave"'


# ---------- idioma base inglês (direção inversa) ----------

def test_com_idioma_base_ingles_o_trecho_falado_e_o_portugues():
    frase = Frase("Ele desistiu da luta.", "He gave up the fight.")
    frase.annotations = [anot(1, frase, "desistiu", "gave up")]

    resultado = composer.compose(frase, {1}, "en")

    assert resultado.ssml == (
        '<speak version="1.0" xml:lang="en-US">He <lang xml:lang="pt-BR">desistiu</lang> the fight.</speak>'
    )
    assert resultado.text == "He gave up the fight."
    assert resultado.swaps == [Swap(start=3, end=10, text="gave up", spoken="desistiu", lang="pt-BR", annotation_id=1)]
    assert resultado.text[3:10] == "gave up"


def test_idioma_base_desconhecido_levanta_erro():
    with pytest.raises(ValueError, match="idioma"):
        composer.compose(LUZ, set(), "fr")


def test_o_resultado_e_imutavel():
    resultado = composer.compose(LUZ, {1}, "pt")
    assert isinstance(resultado, ComposedText)
    with pytest.raises(AttributeError):
        resultado.ssml = "x"  # type: ignore[misc]


# ---------- densidade ----------

def candidatos(n: int, kind: str = KIND) -> list[Anot]:
    return [Anot(i + 1, kind, 0, 1, "x", i, i + 1, "x") for i in range(n)]


def escolhidos(n: int, densidade: str) -> list[int]:
    """Posições (0 a n-1) dos candidatos escolhidos."""
    ids = PhrasalVerbStrategy().select(candidatos(n), densidade)
    return sorted(i - 1 for i in ids)


def test_as_proporcoes_sao_constantes_nomeadas():
    assert DENSITY_SHARE == {"low": 0.15, "medium": 0.35, "high": 0.60}


@pytest.mark.parametrize("n, baixa, media, alta", [(20, 3, 7, 12), (100, 15, 35, 60), (9, 1, 3, 5), (31, 5, 11, 19)])
def test_as_tres_densidades_selecionam_cerca_de_15_35_e_60_por_cento(n, baixa, media, alta):
    assert (len(escolhidos(n, "low")), len(escolhidos(n, "medium")), len(escolhidos(n, "high"))) == (baixa, media, alta)


def test_cada_densidade_seleciona_mais_que_a_anterior():
    for n in (5, 12, 40):
        assert len(escolhidos(n, "low")) <= len(escolhidos(n, "medium")) <= len(escolhidos(n, "high"))


@pytest.mark.parametrize("densidade", ["low", "medium", "high"])
def test_o_espacamento_entre_os_escolhidos_e_regular(densidade):
    posicoes = escolhidos(60, densidade)
    intervalos = [b - a for a, b in zip(posicoes, posicoes[1:])]
    assert max(intervalos) - min(intervalos) <= 1  # nunca dois escolhidos colados e um buraco grande
    assert posicoes[0] <= max(intervalos) and (59 - posicoes[-1]) <= max(intervalos)  # nem tudo no começo ou no fim


def test_cada_escolhido_cai_no_meio_de_uma_faixa_igual_da_historia():
    # 20 candidatos, 3 escolhidos: faixas de 6,67 candidatos, com o escolhido no meio de cada uma
    assert escolhidos(20, "low") == [3, 10, 16]
    assert escolhidos(10, "medium") == [1, 3, 6, 8]  # 35% de 10 = 4 (3,5 arredonda para cima)


def test_pelo_menos_um_trecho_e_trocado_quando_ha_candidatos():
    assert len(escolhidos(3, "low")) == 1  # 15% de 3 daria 0
    assert len(escolhidos(1, "low")) == 1


def test_sem_candidatos_nao_seleciona_nada():
    assert PhrasalVerbStrategy().select([], "high") == set()


def test_com_um_unico_candidato_todas_as_densidades_o_escolhem():
    for densidade in ("low", "medium", "high"):
        assert escolhidos(1, densidade) == [0]


def test_nunca_escolhe_mais_do_que_existe():
    for n in range(1, 30):
        assert len(escolhidos(n, "high")) <= n


def test_o_mesmo_pedido_gera_sempre_a_mesma_selecao():
    primeira = PhrasalVerbStrategy().select(candidatos(37), "medium")
    for _ in range(20):
        assert PhrasalVerbStrategy().select(candidatos(37), "medium") == primeira


def test_so_conta_e_escolhe_anotacoes_com_equivalente_em_portugues():
    com = candidatos(10)
    sem = [Anot(100 + i, KIND, None, None, None, 0, 1, "x") for i in range(10)]
    # as 10 sem equivalente não entram nem na conta: 35% de 10 candidatos, e não de 20
    escolhidas = PhrasalVerbStrategy().select(com + sem, "medium")
    assert len(escolhidas) == 4  # round(3,5) = 4
    assert not any(i >= 100 for i in escolhidas)


def test_ignora_anotacoes_de_outro_tipo():
    mistas = candidatos(10) + [Anot(200 + i, "difficult_word", 0, 1, "x", 0, 1, "x") for i in range(10)]
    escolhidas = PhrasalVerbStrategy().select(mistas, "high")
    assert len(escolhidas) == 6 and all(i <= 10 for i in escolhidas)


def test_densidade_desconhecida_levanta_erro_claro():
    with pytest.raises(ValueError, match="densidade"):
        PhrasalVerbStrategy().select(candidatos(5), "extrema")


# ---------- fábrica ----------

def test_a_fabrica_devolve_a_estrategia_do_tipo_de_trecho_do_filtro():
    estrategia = SwapStrategyFactory.create("phrasal_verbs")
    assert isinstance(estrategia, PhrasalVerbStrategy)
    assert estrategia.kind == KIND  # o filtro diz "phrasal_verbs" (plural) e a anotação, "phrasal_verb"


def test_a_fabrica_lista_os_tipos_disponiveis():
    assert SwapStrategyFactory.types() == ["phrasal_verbs"]


def test_a_fabrica_levanta_erro_claro_para_tipo_sem_estrategia():
    with pytest.raises(UnknownSwapStrategyError) as erro:
        SwapStrategyFactory.create("idioms")
    assert "idioms" in str(erro.value) and "phrasal_verbs" in str(erro.value)
    assert isinstance(erro.value, ValueError)


# ---------- seleção na história inteira ----------

def historia(n_frases: int, por_frase: int = 2) -> list[Frase]:
    frases = []
    for pos in range(n_frases):
        f = Frase("Ele desistiu e acordou.", "He gave up and woke up.", id=pos + 1, position=pos)
        f.annotations = [
            anot(pos * 10 + 1, f, "desistiu", "gave up"),
            anot(pos * 10 + 2, f, "acordou", "woke up"),
        ][:por_frase]
        frases.append(f)
    return frases


def test_a_densidade_vale_para_a_historia_inteira_e_nao_por_frase():
    frases = historia(10)  # 20 candidatos
    escolhidas = composer.select_swaps(frases, ["phrasal_verbs"], "low")
    assert len(escolhidas) == 3  # 15% de 20, espalhados pela história

    por_frase = [sum(1 for a in f.annotations if a.id in escolhidas) for f in frases]
    assert sum(por_frase) == 3 and por_frase.count(0) >= 5  # não é "um por frase"


def test_a_selecao_da_historia_nao_depende_da_ordem_em_que_as_frases_chegam():
    frases = historia(12)
    esperado = composer.select_swaps(frases, ["phrasal_verbs"], "medium")
    for semente in range(10):
        embaralhadas = frases[:]
        random.Random(semente).shuffle(embaralhadas)
        assert composer.select_swaps(embaralhadas, ["phrasal_verbs"], "medium") == esperado


def test_tipo_de_trecho_sem_estrategia_na_selecao_da_historia_levanta_erro():
    with pytest.raises(UnknownSwapStrategyError):
        composer.select_swaps(historia(2), ["idioms"], "low")


def test_historia_sem_anotacoes_nao_seleciona_nada():
    vazias = [Frase("Oi.", "Hi.", id=1, position=0)]
    assert composer.select_swaps(vazias, ["phrasal_verbs"], "high") == set()


def test_selecionar_e_compor_a_historia_inteira():
    frases = historia(10)
    escolhidas = composer.select_swaps(frases, ["phrasal_verbs"], "high")
    textos = [composer.compose(f, escolhidas, "pt") for f in frases]
    assert sum(len(t.swaps) for t in textos) == len(escolhidas) == 12


# ---------- com as histórias reais do seed (banco de teste) ----------

@pytest.fixture
def historias_reais(db_session):
    from app.modules.stories.annotator import TextAnnotator
    from app.modules.stories.repository import SegmentRepository, StoryRepository
    from app.modules.stories.seed.loader import load_seed

    load_seed(db_session)
    TextAnnotator.with_defaults(db_session).annotate_all()
    titulos = ["A Raposa e as Uvas", "A Lebre e a Tartaruga", "O Patinho Feio"]
    historias = {}
    for titulo in titulos:
        story = StoryRepository(db_session).get_by_title(titulo)
        historias[titulo] = SegmentRepository(db_session).list_by_story(story.id)
    return historias


@pytest.mark.parametrize("densidade, esperado", [("low", 0.15), ("medium", 0.35), ("high", 0.60)])
def test_historias_reais_trocam_a_fracao_pedida_e_geram_ssml_valido(historias_reais, densidade, esperado):
    for titulo, segmentos in historias_reais.items():
        candidatos_reais = [a for s in segmentos for a in s.annotations if a.pt_start is not None and a.kind == "phrasal_verb"]
        escolhidas = composer.select_swaps(segmentos, ["phrasal_verbs"], densidade)

        assert abs(len(escolhidas) - len(candidatos_reais) * esperado) <= 1, titulo
        for segmento in segmentos:
            composto = composer.compose(segmento, escolhidas, "pt")
            xml(composto.ssml)  # XML válido
            for swap in composto.swaps:
                assert segmento.text_pt[swap.start : swap.end] == swap.text


def test_historias_reais_geram_sempre_o_mesmo_ssml(historias_reais):
    segmentos = historias_reais["A Lebre e a Tartaruga"]

    def ssmls():
        escolhidas = composer.select_swaps(segmentos, ["phrasal_verbs"], "medium")
        return [composer.compose(s, escolhidas, "pt").ssml for s in segmentos]

    primeira = ssmls()
    assert all(ssmls() == primeira for _ in range(5))


def test_o_ssml_composto_e_aceito_pelo_provedor_de_tts_falso(historias_reais):
    fake = FakeTTSProvider()
    segmentos = historias_reais["O Patinho Feio"]
    escolhidas = composer.select_swaps(segmentos, ["phrasal_verbs"], "high")

    for segmento in segmentos:
        composto = composer.compose(segmento, escolhidas, "pt")
        resultado = fake.synthesize(composto.ssml, "voz")
        assert resultado.format == "wav" and resultado.duration_ms > 0

    assert len(fake.calls) == len(segmentos)
    assert any("<lang" in c.ssml for c in fake.calls)  # as trocas chegam ao TTS
