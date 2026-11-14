"""Comando que deixa o áudio de todas as histórias pronto, em todos os casos, já emendado num arquivo único.

    python -m app.modules.audio.pregenerate [--story-id N] [--scenario A|B|C]... [--density low|medium|high]... [--dry-run]

Para cada história e cada combinação de filtro aceita pela API (`SCENARIOS`: o Cenário A com phrasal verbs, o B com
palavras difíceis nos dois níveis e o C com vocabulário avançado, cada um nas três densidades) gera o áudio das
frases (o cache global reaproveita as frases iguais, então o custo real é bem menor que o número de combinações) e
monta o áudio único, como `GET /stories/{id}/audio/full` faria na primeira vez. Assim a primeira escuta de qualquer
usuário, com qualquer filtro, já encontra tudo pronto. Pode ser repetido: o que já está pronto não é refeito.

Usa o provedor de TTS e a voz configurados no ambiente (TTS_PROVIDER, TTS_VOICE_ID, TTS_VOICE_ID_PT/EN).
"""
import argparse
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.integrations.storage import ObjectStorage, StorageError, get_storage
from app.integrations.tts import TTSProvider, get_tts_provider
from app.modules.audio.facade import GenerationResult, build_facade
from app.modules.audio.full_track import FullTrackBuilder, UnsupportedAudioFormat
from app.modules.audio.models import STATUS_READY
from app.modules.audio.repository import AudioAssetRepository, compute_rules_hash
from app.modules.filters.schemas import SCENARIOS, FilterRules
from app.modules.stories.service import StoryService

SCENARIO_LETTERS = "ABCDEFGH"
DENSITIES = ("low", "medium", "high")


@dataclass(frozen=True)
class Combo:
    story_id: int
    scenario: str  # letra do cenário (A, B, C)
    density: str
    rules: dict[str, Any]  # regras já normalizadas, as mesmas que a API usa para calcular o hash

    @property
    def label(self) -> str:
        level = self.rules.get("word_level")
        return f"{self.scenario}{'/' + level if level else ''} · {self.density}"


@dataclass
class ComboResult:
    combo: Combo
    total: int = 0
    generated: int = 0
    cached: int = 0
    skipped: int = 0  # já estavam prontas
    failed: int = 0
    duration_ms: int | None = None  # do áudio único, quando montado
    error: str | None = None


def build_combos(
    story_ids: Iterable[int], scenarios: Sequence[str] | None = None, densities: Sequence[str] | None = None
) -> list[Combo]:
    """Todas as combinações história x filtro aceitas pela API (a tabela `SCENARIOS`), filtradas pelas opções."""
    wanted_scenarios = {s.upper() for s in scenarios} if scenarios else None
    wanted_densities = set(densities) if densities else None
    combos: list[Combo] = []
    for story_id in story_ids:
        for index, scenario in enumerate(SCENARIOS):
            letter = SCENARIO_LETTERS[index]
            if wanted_scenarios is not None and letter not in wanted_scenarios:
                continue
            for level in scenario.word_levels or [None]:
                for density in DENSITIES:
                    if wanted_densities is not None and density not in wanted_densities:
                        continue
                    raw: dict[str, Any] = {
                        "base_language": scenario.base_language,
                        "segment_types": list(scenario.segment_types),
                        "density": density,
                    }
                    if level:
                        raw["word_level"] = level
                    if scenario.progressions[0] != "fixed":
                        raw["progression"] = scenario.progressions[0]
                    combos.append(Combo(story_id, letter, density, FilterRules.model_validate(raw).model_dump()))
    return combos


def pregenerate(
    db: Session,
    tts: TTSProvider,
    storage: ObjectStorage,
    combos: Sequence[Combo],
    *,
    voice_for: Callable[[str], str],
    on_result: Callable[[ComboResult], None] | None = None,
    **facade_kwargs: Any,
) -> list[ComboResult]:
    """Gera e junta o áudio de cada combinação. Uma combinação que falha não interrompe as outras."""
    results: list[ComboResult] = []
    for combo in combos:
        result = ComboResult(combo)
        voice = voice_for(combo.rules["base_language"])
        try:
            facade = build_facade(db, tts, storage, voice, **facade_kwargs)
            generation: GenerationResult = facade.generate(combo.story_id, combo.rules)
            result.total = (
                len(generation.generated) + len(generation.cached) + len(generation.skipped) + len(generation.failed)
            )
            result.generated, result.cached = len(generation.generated), len(generation.cached)
            result.skipped, result.failed = len(generation.skipped), len(generation.failed)
            result.duration_ms = _join(db, storage, combo, voice)
        except LookupError as exc:  # história inexistente
            result.error = str(exc)
        except (StorageError, UnsupportedAudioFormat) as exc:
            result.error = f"não foi possível montar o áudio único: {exc}"
        results.append(result)
        if on_result:
            on_result(result)
    return results


def _join(db: Session, storage: ObjectStorage, combo: Combo, voice: str) -> int | None:
    """Monta o áudio único das frases prontas (as que falharam ficam de fora). None se nenhuma ficou pronta."""
    _, segments = StoryService.from_session(db).get_segments(combo.story_id)
    by_segment = {
        a.segment_id: a
        for a in AudioAssetRepository(db).list_by_story(
            combo.story_id, rules_hash=compute_rules_hash(combo.rules), voice_id=voice
        )
    }
    ready = [by_segment[s.id] for s in segments if s.id in by_segment and by_segment[s.id].status == STATUS_READY]
    if not ready:
        return None
    return FullTrackBuilder(storage).build(ready, {s.id: s.position for s in segments}).duration_ms


def format_result(result: ComboResult, titles: dict[int, str]) -> str:
    head = f"{titles.get(result.combo.story_id, result.combo.story_id)} | {result.combo.label}"
    if result.error:
        return f"{head}: ERRO ({result.error})"
    parts = [
        f"{result.total} frases ({result.generated} sintetizadas, {result.cached} do cache, "
        f"{result.skipped} já prontas, {result.failed} falhas)"
    ]
    if result.duration_ms is not None:
        parts.append(f"áudio único de {result.duration_ms / 1000:.1f} s")
    return f"{head}: " + ", ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.audio.pregenerate",
        description=(
            "Gera o áudio de todas as histórias em todos os cenários e densidades e monta o áudio único de cada "
            "combinação, para a primeira escuta já encontrar tudo pronto. Gasta caracteres do TTS na primeira vez; "
            "depois o cache reaproveita. Use --dry-run para ver o que seria feito."
        ),
    )
    parser.add_argument("--story-id", type=int, action="append", help="só esta história (pode repetir; padrão: todas)")
    parser.add_argument(
        "--scenario", action="append", choices=list(SCENARIO_LETTERS[: len(SCENARIOS)]),
        help="só este cenário: A (phrasal verbs), B (palavras difíceis) ou C (vocabulário avançado); pode repetir",
    )
    parser.add_argument(
        "--density", action="append", choices=list(DENSITIES), help="só esta densidade (pode repetir; padrão: as três)"
    )
    parser.add_argument("--dry-run", action="store_true", help="lista as combinações, sem gerar nem gastar nada")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    tts: TTSProvider | None = None,
    storage: ObjectStorage | None = None,
    settings: Settings | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()
    with (session_factory or SessionLocal)() as db:
        stories = StoryService.from_session(db).list_stories()
        titles = {s.id: s.title for s in stories}
        story_ids = args.story_id or [s.id for s in stories]
        unknown = [i for i in story_ids if i not in titles]
        if unknown:
            print(f"História(s) inexistente(s): {', '.join(map(str, unknown))}", file=sys.stderr)
            return 2
        combos = build_combos(story_ids, args.scenario, args.density)
        if not combos:
            print("Nenhuma combinação para gerar.", file=sys.stderr)
            return 2

        if args.dry_run:
            print(f"[simulação, nada foi gerado] {len(combos)} combinações:")
            for combo in combos:
                print(f"  {titles[combo.story_id]} | {combo.label} | voz {settings.voice_for(combo.rules['base_language'])}")
            return 0

        results = pregenerate(
            db,
            tts or get_tts_provider(),
            storage or get_storage(),
            combos,
            voice_for=settings.voice_for,
            on_result=lambda r: print(format_result(r, titles), flush=True),
        )

    failed = [r for r in results if r.error or r.failed]
    print(
        f"\n{len(results)} combinações: {sum(r.generated for r in results)} frases sintetizadas, "
        f"{sum(r.cached for r in results)} do cache, {sum(r.skipped for r in results)} já prontas; "
        f"{len(failed)} combinação(ões) com problema."
    )
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
