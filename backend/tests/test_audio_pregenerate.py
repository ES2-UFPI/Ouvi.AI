"""Testes do comando que pré-gera o áudio de todas as histórias, em todos os cenários, e monta o áudio único.

Provedor falso e armazenamento em memória: sem rede, sem chave e sem custo. As histórias são criadas dentro da
transação do teste (desfeita no fim), então o banco de desenvolvimento não é tocado.
"""
from contextlib import nullcontext

import pytest

from app.core.config import get_settings
from app.integrations.tts import get_tts_provider
from app.main import app
from app.modules.audio.models import STATUS_READY
from app.modules.audio.pregenerate import build_combos, main, pregenerate
from app.modules.audio.repository import AudioAssetRepository, compute_rules_hash
from tests.test_audio_facade import TTSComFalhas
from tests.test_audio_full_track import completo
from tests.test_audio_generation_api import REGRAS, ana, criar_filtro, sessoes, status_de, storage, tts  # noqa: F401
from tests.test_audio_voices import historia  # noqa: F401  (história com phrasal verbs e palavras difíceis)


def voz(base_language: str) -> str:
    return get_settings().voice_for(base_language)


def rodar(db_session, tts, storage, combos, **kwargs):
    return pregenerate(db_session, tts, storage, combos, voice_for=voz, sleep=lambda _: None, **kwargs)


# ---------- as combinações ----------

def test_gera_todas_as_combinacoes_aceitas_pela_api():
    combos = build_combos([1])

    # A: 3 densidades; B: 2 níveis x 3 densidades; C: 3 densidades
    assert len(combos) == 12
    assert [c.scenario for c in combos] == ["A"] * 3 + ["B"] * 6 + ["C"] * 3
    a, b, c = combos[0], combos[3], combos[9]
    assert a.rules["segment_types"] == ["phrasal_verbs"] and a.rules["base_language"] == "pt"
    assert b.rules["segment_types"] == ["difficult_words"] and b.rules["base_language"] == "en"
    assert {x.rules["word_level"] for x in combos if x.scenario == "B"} == {"intermediate", "advanced"}
    assert c.rules["segment_types"] == ["advanced_vocabulary"] and c.rules["progression"] == "increasing"
    assert all(x.rules["density"] == x.density for x in combos)


def test_as_opcoes_filtram_por_cenario_e_por_densidade():
    assert [c.scenario for c in build_combos([1], scenarios=["c"])] == ["C"] * 3
    assert [c.density for c in build_combos([1], scenarios=["A"], densities=["high"])] == ["high"]
    assert len(build_combos([1, 2], scenarios=["A", "B"], densities=["low", "high"])) == 2 * (2 + 4)
    assert build_combos([]) == []


# ---------- gerar e juntar ----------

def test_gera_as_frases_e_monta_o_audio_unico_de_cada_combinacao(db_session, historia, tts, storage):
    combos = build_combos([historia.id], scenarios=["A", "C"], densities=["high"])

    resultados = rodar(db_session, tts, storage, combos)

    assert [r.combo.scenario for r in resultados] == ["A", "C"]
    for r in resultados:
        assert r.error is None and r.failed == 0 and r.total == 3
        assert r.duration_ms and r.duration_ms > 0
        ativos = AudioAssetRepository(db_session).list_by_story(
            historia.id, rules_hash=compute_rules_hash(r.combo.rules), voice_id=voz(r.combo.rules["base_language"])
        )
        assert len(ativos) == 3 and all(a.status == STATUS_READY for a in ativos)
        assert r.duration_ms == sum(a.duration_ms for a in ativos)  # a duração do arquivo único é a soma das frases
    assert len([k for k in storage._objects if k.startswith("full/")]) == 2


def test_repetir_o_comando_nao_chama_o_tts_de_novo(db_session, historia, tts, storage):
    combos = build_combos([historia.id], scenarios=["A"], densities=["high"])
    rodar(db_session, tts, storage, combos)
    chamadas = len(tts.calls)

    segunda = rodar(db_session, tts, storage, combos)

    assert len(tts.calls) == chamadas
    assert segunda[0].skipped == 3 and segunda[0].generated == 0
    assert len([k for k in storage._objects if k.startswith("full/")]) == 1  # o arquivo único também é reaproveitado


def test_densidades_que_escolhem_as_mesmas_trocas_reaproveitam_tudo_pelo_cache(db_session, historia, tts, storage):
    # Com 3 candidatas, a densidade baixa e a média trocam a mesma palavra: o SSML das frases é idêntico
    baixa, media = build_combos([historia.id], scenarios=["A"], densities=["low", "medium"])
    assert compute_rules_hash(baixa.rules) != compute_rules_hash(media.rules)  # são filtros diferentes

    rodar(db_session, tts, storage, [baixa])
    assert len(tts.calls) == 3
    resultado = rodar(db_session, tts, storage, [media])[0]

    assert len(tts.calls) == 3  # nenhuma frase foi sintetizada de novo
    assert resultado.cached == 3 and resultado.generated == 0


def test_a_primeira_escuta_pela_api_ja_encontra_tudo_pronto(api, ana, historia, tts, storage, db_session):
    """O filtro que o usuário salva tem as mesmas regras (e o mesmo hash) das combinações pré-geradas."""
    combo = build_combos([historia.id], scenarios=["A"], densities=["high"])[0]
    rodar(db_session, tts, storage, [combo])
    chamadas = len(tts.calls)

    filtro = criar_filtro(api, ana, historia.id, REGRAS)  # Cenário A, densidade alta

    assert status_de(api, ana, historia.id, filtro).json()["state"] == "ready"
    unico = completo(api, ana, historia.id, filtro)
    assert unico.status_code == 200 and len(unico.json()["segments"]) == 3
    assert len(tts.calls) == chamadas  # nada foi sintetizado na primeira escuta


def test_uma_frase_que_falha_nao_derruba_as_outras_nem_o_audio_unico(db_session, historia, storage):
    quebrado = TTSComFalhas("desligou", retryable=False)  # só a frase 2 ("Ele desligou a luz.")
    combos = build_combos([historia.id], scenarios=["A"], densities=["high"])

    r = rodar(db_session, quebrado, storage, combos)[0]

    assert (r.failed, r.error) == (1, None)
    assert r.total == 3 and r.duration_ms and r.duration_ms > 0  # o áudio único sai com as frases boas


def test_se_nenhuma_frase_fica_pronta_nao_monta_o_audio_unico(db_session, historia, storage):
    quebrado = TTSComFalhas("", retryable=False)  # falha em todas as frases
    combos = build_combos([historia.id], scenarios=["A"], densities=["high"])

    r = rodar(db_session, quebrado, storage, combos)[0]

    assert r.failed == 3 and r.duration_ms is None
    assert not [k for k in storage._objects if k.startswith("full/")]


def test_historia_inexistente_vira_erro_da_combinacao_e_as_outras_seguem(db_session, historia, tts, storage):
    combos = build_combos([999_999, historia.id], scenarios=["A"], densities=["high"])

    erro, boa = rodar(db_session, tts, storage, combos)

    assert erro.error and "999999" in erro.error
    assert boa.error is None and boa.duration_ms


# ---------- o comando ----------

def executar(db_session, tts, storage, *args):
    return main(list(args), session_factory=lambda: nullcontext(db_session), tts=tts, storage=storage)


def test_dry_run_lista_as_combinacoes_sem_gerar_nada(db_session, historia, tts, storage, capsys):
    codigo = executar(db_session, tts, storage, "--story-id", str(historia.id), "--scenario", "C", "--dry-run")

    saida = capsys.readouterr().out
    assert codigo == 0 and "[simulação" in saida and saida.count("C ·") == 3
    assert tts.calls == [] and not storage._objects


def test_o_comando_gera_e_resume(db_session, historia, tts, storage, capsys):
    codigo = executar(db_session, tts, storage, "--story-id", str(historia.id), "--scenario", "A", "--density", "high")

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "A · high: 3 frases (3 sintetizadas" in saida and "áudio único de" in saida
    assert "1 combinações" in saida and "0 combinação(ões) com problema" in saida


def test_o_comando_sai_com_erro_quando_alguma_frase_falha(db_session, historia, storage, capsys):
    quebrado = TTSComFalhas("desligou", retryable=False)
    codigo = executar(db_session, quebrado, storage, "--story-id", str(historia.id), "--scenario", "A", "--density", "high")
    assert codigo == 1 and "1 combinação(ões) com problema" in capsys.readouterr().out


def test_historia_desconhecida_no_comando_responde_2(db_session, historia, tts, storage, capsys):
    assert executar(db_session, tts, storage, "--story-id", "999999") == 2
    assert "inexistente" in capsys.readouterr().err
    assert tts.calls == []
