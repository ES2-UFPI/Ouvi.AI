"""Testes da AudioGenerationFacade (#85): pipeline NLP -> TTS -> armazenamento.

Usam o FakeTTSProvider, o InMemoryStorage e o banco de teste (`db_session`, desfeito no fim de cada teste):
sem rede, sem chave e sem MinIO.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.integrations.storage import InMemoryStorage
from app.integrations.tts import FakeCall, FakeTTSProvider, TTSError
from app.modules.audio import facade as facade_module
from app.modules.audio.facade import AudioGenerationFacade, build_facade, run_generation
from app.modules.audio.models import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
    STATUS_READY,
    AudioAsset,
)
from app.modules.audio.repository import AudioAssetRepository, compute_rules_hash
from app.modules.stories.models import KIND_PHRASAL_VERB, Annotation, Segment, Story

REGRAS = {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "high"}
VOZ = "voz-de-teste"

# Três frases, cada uma com um phrasal verb alinhado ao português. Com densidade alta (60%), 2 dos 3 são trocados
FRASES = [
    ("She gave up the race.", "Ela desistiu da corrida.", "gave up", "desistiu"),
    ("He turned off the light.", "Ele desligou a luz.", "turned off", "desligou"),
    ("They set off early.", "Eles partiram cedo.", "set off", "partiram"),
]


def nova_historia() -> Story:
    segments = []
    for i, (en, pt, trecho_en, trecho_pt) in enumerate(FRASES):
        en_start, pt_start = en.index(trecho_en), pt.index(trecho_pt)
        segments.append(
            Segment(
                position=i,
                text_en=en,
                text_pt=pt,
                annotations=[
                    Annotation(
                        kind=KIND_PHRASAL_VERB,
                        lemma=trecho_en,
                        en_start=en_start,
                        en_end=en_start + len(trecho_en),
                        en_text=trecho_en,
                        pt_start=pt_start,
                        pt_end=pt_start + len(trecho_pt),
                        pt_text=trecho_pt,
                    )
                ],
            )
        )
    return Story(title="Histórias curtas", language="en", segments=segments)


@pytest.fixture
def historia(db_session) -> Story:
    story = nova_historia()
    db_session.add(story)
    db_session.commit()
    return story


@pytest.fixture
def tts() -> FakeTTSProvider:
    return FakeTTSProvider()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def make_facade(db_session, storage):
    def _make(tts, **kwargs) -> AudioGenerationFacade:
        kwargs.setdefault("sleep", lambda _: None)
        return build_facade(db_session, tts, storage, VOZ, **kwargs)

    return _make


def assets_da(db_session, story: Story) -> list[AudioAsset]:
    db_session.expire_all()
    stmt = (
        select(AudioAsset)
        .join(Segment, Segment.id == AudioAsset.segment_id)
        .where(AudioAsset.story_id == story.id)
        .order_by(Segment.position)
    )
    return list(db_session.scalars(stmt))


class TTSComFalhas(FakeTTSProvider):
    """Provedor falso que falha nas frases cujo SSML contém `trecho`: `vezes` falhas, depois funciona."""

    def __init__(self, trecho: str, *, retryable: bool, vezes: int = 1_000) -> None:
        super().__init__()
        self.trecho = trecho
        self.retryable = retryable
        self.restantes = vezes

    def synthesize(self, ssml: str, voice_id: str):
        if self.trecho in ssml and self.restantes > 0:
            self.calls.append(FakeCall(ssml, voice_id))
            self.restantes -= 1
            raise TTSError("fornecedor sobrecarregado" if self.retryable else "SSML recusado", retryable=self.retryable)
        return super().synthesize(ssml, voice_id)


# ---------- caminho feliz ----------

def test_gera_um_audio_ready_por_frase_com_o_arquivo_no_armazenamento(historia, db_session, tts, storage, make_facade):
    result = make_facade(tts).generate(historia.id, REGRAS, user_id=1)

    assets = assets_da(db_session, historia)
    assert [a.segment_id for a in assets] == [s.id for s in historia.segments]
    assert all(a.status == STATUS_READY for a in assets)
    assert result.generated == [s.id for s in historia.segments]
    for asset in assets:
        assert asset.rules_hash == compute_rules_hash(REGRAS)
        assert asset.voice_id == VOZ
        assert asset.format == "wav"
        assert asset.duration_ms > 0
        assert storage.get(asset.storage_key)[:4] == b"RIFF"  # o arquivo existe e é um WAV
    assert len(tts.calls) == 3
    assert all(call.voice_id == VOZ for call in tts.calls)


def test_o_ssml_enviado_tem_lang_en_us_nos_trechos_trocados(historia, tts, make_facade):
    make_facade(tts).generate(historia.id, REGRAS)

    trocados = [c.ssml for c in tts.calls if '<lang xml:lang="en-US">' in c.ssml]
    assert len(trocados) == 2  # densidade alta: 2 dos 3 phrasal verbs
    for ssml in trocados:
        assert ssml.startswith('<speak version="1.0" xml:lang="pt-BR">')
    falados = {trecho_en for _, _, trecho_en, _ in FRASES if any(f'en-US">{trecho_en}</lang>' in s for s in trocados)}
    assert len(falados) == 2


def test_a_segunda_chamada_nao_chama_o_tts_de_novo(historia, db_session, tts, make_facade):
    make_facade(tts).generate(historia.id, REGRAS)
    chamadas = len(tts.calls)

    result = make_facade(tts).generate(historia.id, REGRAS)

    assert len(tts.calls) == chamadas
    assert result.generated == [] and len(result.skipped) == 3
    assert len(assets_da(db_session, historia)) == 3  # nenhum registro duplicado


def test_regras_diferentes_geram_outro_audio(historia, db_session, tts, make_facade):
    make_facade(tts).generate(historia.id, REGRAS)
    make_facade(tts).generate(historia.id, {**REGRAS, "density": "low"})

    assert len(tts.calls) == 6
    assert len(assets_da(db_session, historia)) == 6


def test_a_primeira_frase_fica_pronta_antes_das_demais(historia, db_session, make_facade):
    estados_vistos: list[list[str]] = []

    class TTSQueObserva(FakeTTSProvider):
        def synthesize(self, ssml, voice_id):
            # Lê o banco no momento de cada síntese: o que já foi confirmado até ali
            estados_vistos.append([a.status for a in assets_da(db_session, historia)])
            return super().synthesize(ssml, voice_id)

    make_facade(TTSQueObserva()).generate(historia.id, REGRAS)

    assert estados_vistos == [
        [STATUS_GENERATING, STATUS_PENDING, STATUS_PENDING],
        [STATUS_READY, STATUS_GENERATING, STATUS_PENDING],
        [STATUS_READY, STATUS_READY, STATUS_GENERATING],
    ]


# ---------- falhas ----------

def test_falha_recuperavel_tenta_de_novo_e_termina_ready(historia, db_session, make_facade):
    esperas: list[float] = []
    tts = TTSComFalhas("desligou", retryable=True, vezes=2)

    make_facade(tts, sleep=esperas.append).generate(historia.id, REGRAS)

    assert all(a.status == STATUS_READY for a in assets_da(db_session, historia))
    assert esperas == [1.0, 2.0]  # espera crescente entre as tentativas


def test_falha_definitiva_marca_so_aquela_frase_como_failed(historia, db_session, make_facade):
    tts = TTSComFalhas("desligou", retryable=True)  # falha sempre

    result = make_facade(tts, max_attempts=3).generate(historia.id, REGRAS)

    assets = assets_da(db_session, historia)
    assert [a.status for a in assets] == [STATUS_READY, STATUS_FAILED, STATUS_READY]
    assert assets[1].error == "fornecedor sobrecarregado"
    assert assets[1].storage_key is None
    assert result.failed == [historia.segments[1].id]


def test_erro_nao_recuperavel_falha_sem_tentar_de_novo(historia, db_session, make_facade):
    esperas: list[float] = []
    tts = TTSComFalhas("desligou", retryable=False)

    make_facade(tts, sleep=esperas.append).generate(historia.id, REGRAS)

    assert [a.status for a in assets_da(db_session, historia)] == [STATUS_READY, STATUS_FAILED, STATUS_READY]
    assert esperas == []
    assert tts.restantes == 1_000 - 1  # uma única chamada para a frase que falhou


def test_a_frase_que_falhou_e_tentada_de_novo_na_proxima_geracao(historia, db_session, make_facade):
    make_facade(TTSComFalhas("desligou", retryable=False)).generate(historia.id, REGRAS)
    tts = FakeTTSProvider()

    result = make_facade(tts).generate(historia.id, REGRAS)

    assert len(tts.calls) == 1  # só a que tinha falhado
    assert result.generated == [historia.segments[1].id]
    assert all(a.status == STATUS_READY for a in assets_da(db_session, historia))


def test_historia_inexistente_levanta_lookup_error(db_session, tts, make_facade):
    with pytest.raises(LookupError):
        make_facade(tts).generate(999_999_999, REGRAS)


# ---------- frases presas ----------

def test_frase_presa_em_generating_e_recuperada_na_proxima_geracao(historia, db_session, tts, make_facade):
    repo = AudioAssetRepository(db_session)
    presa = repo.get_or_create(
        story_id=historia.id, segment_id=historia.segments[0].id, rules_hash=compute_rules_hash(REGRAS), voice_id=VOZ
    )
    repo.start_generation(presa)  # o worker "morreu" aqui
    db_session.execute(
        update(AudioAsset).where(AudioAsset.id == presa.id).values(updated_at=text("now() - interval '1 hour'"))
    )
    db_session.commit()

    make_facade(tts).generate(historia.id, REGRAS)

    assert all(a.status == STATUS_READY for a in assets_da(db_session, historia))
    assert len(tts.calls) == 3


def test_frase_em_generating_recente_nao_e_gerada_de_novo(historia, db_session, tts, make_facade):
    """Uma frase que outro worker acabou de começar não é tocada: nada de gerar duas vezes."""
    repo = AudioAssetRepository(db_session)
    em_curso = repo.get_or_create(
        story_id=historia.id, segment_id=historia.segments[0].id, rules_hash=compute_rules_hash(REGRAS), voice_id=VOZ
    )
    repo.start_generation(em_curso)

    result = make_facade(tts, stale_after=timedelta(minutes=10)).generate(historia.id, REGRAS)

    assert result.skipped == [historia.segments[0].id]
    assert len(tts.calls) == 2


# ---------- sessão própria em segundo plano ----------

def test_run_generation_usa_uma_sessao_propria_e_a_fecha(historia, db_session, tts, storage):
    abertas: list[Session] = []

    def nova_sessao() -> Session:
        # Outra sessão sobre a mesma conexão do teste (para enxergar os dados não confirmados)
        session = Session(bind=db_session.connection(), join_transaction_mode="create_savepoint")
        abertas.append(session)
        return session

    result = run_generation(
        nova_sessao, tts, storage, voice_id=VOZ, story_id=historia.id, rules=REGRAS, user_id=1,
        sleep=lambda _: None,
    )

    assert len(abertas) == 1 and abertas[0] is not db_session
    assert not abertas[0].in_transaction()  # fechada no fim
    assert len(result.generated) == 3
    assert all(a.status == STATUS_READY for a in assets_da(db_session, historia))


def test_run_generation_nao_deixa_o_erro_escapar_e_fecha_a_sessao(db_session, tts, storage):
    abertas: list[Session] = []

    def nova_sessao() -> Session:
        session = Session(bind=db_session.connection(), join_transaction_mode="create_savepoint")
        abertas.append(session)
        return session

    assert run_generation(nova_sessao, tts, storage, voice_id=VOZ, story_id=999_999_999, rules=REGRAS) is None
    assert not abertas[0].in_transaction()


def test_a_facade_so_usa_o_story_service_e_nenhum_repositorio_de_outro_modulo():
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(facade_module))
    importados = {
        node.module for node in ast.walk(arvore) if isinstance(node, ast.ImportFrom) and node.module
    }
    de_outros_modulos = {m for m in importados if m.startswith("app.modules.") and not m.startswith("app.modules.audio")}
    assert "app.modules.stories.service" in de_outros_modulos
    assert not any(m.endswith(".repository") for m in de_outros_modulos)
