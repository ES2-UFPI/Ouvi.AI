"""Leitura e validação dos arquivos JSON do seed. Não acessa o banco de dados."""
import json
from dataclasses import dataclass
from pathlib import Path

SEED_DIR = Path(__file__).parent

LANGUAGES = ("en", "pt")
# Frases curtas facilitam gerar o áudio frase a frase e reaproveitar o cache
MAX_SEGMENT_LENGTH = 200

# Metas de qualidade do conteúdo (critérios da issue)
MIN_SEGMENTS, MAX_SEGMENTS = 10, 25
MIN_PHRASAL_VERBS = 6
MIN_SEPARABLE = 2


class SeedError(Exception):
    """Os arquivos do seed têm problemas. A mensagem lista todos de uma vez."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(f"- {p}" for p in problems))


@dataclass(frozen=True)
class SeedPhrasalVerb:
    """Phrasal verb conhecido de uma frase. Serve de referência para conferir o conteúdo
    e, depois, para o alinhamento e o detector."""

    lemma: str
    en: str
    pt: str
    separable: bool


@dataclass(frozen=True)
class SeedSegment:
    en: str
    pt: str
    phrasal_verbs: tuple[SeedPhrasalVerb, ...]


@dataclass(frozen=True)
class SeedStory:
    title: str
    language: str
    description: str | None
    source: str
    segments: tuple[SeedSegment, ...]
    file: str


def read_seed_files(directory: Path = SEED_DIR) -> list[SeedStory]:
    """Lê todos os `*.json` da pasta, na ordem alfabética, e valida a estrutura.

    Lança `SeedError` com todos os problemas encontrados, em vez de parar no primeiro.
    """
    files = sorted(directory.glob("*.json"))
    problems: list[str] = []
    stories: list[SeedStory] = []

    if not files:
        raise SeedError([f"nenhum arquivo .json em {directory}"])

    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: não foi possível ler o JSON ({exc})")
            continue
        story = _parse_story(raw, path.name, problems)
        if story is not None:
            stories.append(story)

    titles = [s.title for s in stories]
    for title in sorted({t for t in titles if titles.count(t) > 1}):
        problems.append(f"título repetido em mais de um arquivo: {title!r}")

    if problems:
        raise SeedError(problems)
    return stories


def _parse_story(raw: object, file: str, problems: list[str]) -> SeedStory | None:
    start = len(problems)
    if not isinstance(raw, dict):
        problems.append(f"{file}: o JSON deve ser um objeto")
        return None

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip() or title != title.strip():
        problems.append(f"{file}: 'title' deve ser um texto não vazio e sem espaços nas pontas")
    if raw.get("language") not in LANGUAGES:
        problems.append(f"{file}: 'language' deve ser um de {LANGUAGES}")
    source = raw.get("source")
    if not isinstance(source, str) or not source.strip():
        problems.append(f"{file}: 'source' (origem e licença do texto) é obrigatório")
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        problems.append(f"{file}: 'description' deve ser texto")

    raw_segments = raw.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        problems.append(f"{file}: 'segments' deve ser uma lista com pelo menos uma frase")
        return None

    segments = [
        s for i, item in enumerate(raw_segments) if (s := _parse_segment(item, file, i, problems))
    ]

    if len(problems) > start:
        return None
    return SeedStory(
        title=title,
        language=raw["language"],
        description=description,
        source=source,
        segments=tuple(segments),
        file=file,
    )


def _parse_segment(item: object, file: str, index: int, problems: list[str]) -> SeedSegment | None:
    where = f"{file}, frase {index + 1}"
    if not isinstance(item, dict):
        problems.append(f"{where}: deve ser um objeto com 'en' e 'pt'")
        return None

    texts: dict[str, str] = {}
    ok = True
    for key in ("en", "pt"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{where}: '{key}' deve ser um texto não vazio")
            ok = False
        elif value != value.strip():
            problems.append(f"{where}: '{key}' tem espaços no início ou no fim")
            ok = False
        elif len(value) > MAX_SEGMENT_LENGTH:
            problems.append(f"{where}: '{key}' tem {len(value)} caracteres (máximo {MAX_SEGMENT_LENGTH})")
            ok = False
        else:
            texts[key] = value
    if not ok:
        return None

    verbs: list[SeedPhrasalVerb] = []
    for n, pv in enumerate(item.get("phrasal_verbs", [])):
        label = f"{where}, phrasal verb {n + 1}"
        if not isinstance(pv, dict) or not all(
            isinstance(pv.get(k), str) and pv.get(k) for k in ("lemma", "en", "pt")
        ):
            problems.append(f"{label}: precisa de 'lemma', 'en' e 'pt' (textos não vazios)")
            continue
        if pv["en"] not in texts["en"]:
            problems.append(f"{label}: {pv['en']!r} não aparece na frase em inglês")
            continue
        if pv["pt"] not in texts["pt"]:
            problems.append(f"{label}: {pv['pt']!r} não aparece na frase em português")
            continue
        verbs.append(
            SeedPhrasalVerb(pv["lemma"], pv["en"], pv["pt"], bool(pv.get("separable", False)))
        )
    return SeedSegment(texts["en"], texts["pt"], tuple(verbs))


def check_quality(stories: list[SeedStory]) -> list[str]:
    """Confere as metas de conteúdo da issue. Devolve a lista de problemas (vazia se tudo certo)."""
    problems: list[str] = []
    for story in stories:
        name = story.title
        n = len(story.segments)
        if not MIN_SEGMENTS <= n <= MAX_SEGMENTS:
            problems.append(f"{name}: {n} frases (esperado de {MIN_SEGMENTS} a {MAX_SEGMENTS})")

        verbs = [pv for seg in story.segments for pv in seg.phrasal_verbs]
        lemmas = {pv.lemma for pv in verbs}
        if len(lemmas) < MIN_PHRASAL_VERBS:
            problems.append(
                f"{name}: {len(lemmas)} phrasal verbs distintos (mínimo {MIN_PHRASAL_VERBS})"
            )
        separable = [pv for pv in verbs if pv.separable]
        if len(separable) < MIN_SEPARABLE:
            problems.append(f"{name}: {len(separable)} separáveis (mínimo {MIN_SEPARABLE})")
        for pv in separable:
            # Separável tem palavra no meio (objeto entre o verbo e a partícula): "turn the light off"
            if len(pv.en.split()) < 3:
                problems.append(
                    f"{name}: {pv.en!r} está marcado como separável mas não tem palavra entre o verbo e a partícula"
                )
    return problems
