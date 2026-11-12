"""Limpeza do cache de áudio: apaga os blobs pouco usados sem deixar nenhum áudio quebrado.

Para cada blob escolhido, primeiro o BANCO (numa transação): os `AudioAsset` que usavam o blob voltam para
`pending` e o registro do blob sai. Só depois de confirmar, o arquivo é apagado do armazenamento. Se apagar o
arquivo falhar, sobra só um arquivo órfão: nenhum registro aponta para um arquivo que não existe.
"""
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.integrations.storage import ObjectStorage, StorageError
from app.modules.audio.cache.repository import AudioBlobRepository
from app.modules.audio.models import STATUS_PENDING, AudioAsset, AudioBlob

logger = logging.getLogger(__name__)

_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMG]?B)?\s*$", re.IGNORECASE)


def parse_size(text: str) -> int:
    """Converte "500MB", "1.5GB", "2048" (bytes)... em bytes. Levanta ValueError se não entender."""
    match = _SIZE.match(text)
    if not match:
        raise ValueError(f"Tamanho inválido: {text!r} (use, por exemplo, 500MB ou 2GB)")
    number, unit = match.groups()
    return int(float(number) * _UNITS[(unit or "B").upper()])


@dataclass
class PurgedBlob:
    blob_id: int
    storage_key: str
    size_bytes: int
    last_used_at: str
    assets_reset: int = 0


@dataclass
class PurgeReport:
    dry_run: bool
    blobs: list[PurgedBlob] = field(default_factory=list)
    file_errors: list[str] = field(default_factory=list)  # arquivos que não saíram (ficaram órfãos)

    @property
    def freed_bytes(self) -> int:
        return sum(b.size_bytes for b in self.blobs)

    @property
    def assets_reset(self) -> int:
        return sum(b.assets_reset for b in self.blobs)

    def as_dict(self) -> dict:
        data = asdict(self)
        data.update(freed_bytes=self.freed_bytes, assets_reset=self.assets_reset, removed=len(self.blobs))
        return data


def select_blobs(
    blobs: AudioBlobRepository,
    *,
    older_than_days: int | None,
    max_size_bytes: int | None,
    now: datetime,
) -> list[AudioBlob]:
    """Escolhe o que sai. Sem nenhum critério, nada sai.

    - `older_than_days`: os sem uso há mais que o prazo;
    - `max_size_bytes`: os menos usados recentemente, até o que sobra caber no limite.
    """
    chosen: list[AudioBlob] = []
    if older_than_days is not None:
        chosen.extend(blobs.list_unused_since(now - timedelta(days=older_than_days)))
    if max_size_bytes is not None:
        chosen_ids = {b.id for b in chosen}
        remaining = [b for b in blobs.list_least_recently_used() if b.id not in chosen_ids]
        total = sum(b.size_bytes for b in remaining)
        for blob in remaining:  # do uso mais antigo para o mais recente
            if total <= max_size_bytes:
                break
            chosen.append(blob)
            total -= blob.size_bytes
    return chosen


def purge(
    db: Session,
    storage: ObjectStorage,
    *,
    older_than_days: int | None = None,
    max_size_bytes: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> PurgeReport:
    """Apaga (ou, com `dry_run`, só lista) os blobs escolhidos por `select_blobs`."""
    if older_than_days is not None and older_than_days < 0:
        raise ValueError("--older-than não pode ser negativo")
    if max_size_bytes is not None and max_size_bytes < 0:
        raise ValueError("--max-size não pode ser negativo")

    repo = AudioBlobRepository(db)
    now = now or datetime.now(timezone.utc)
    report = PurgeReport(dry_run=dry_run)

    for blob in select_blobs(repo, older_than_days=older_than_days, max_size_bytes=max_size_bytes, now=now):
        item = PurgedBlob(blob.id, blob.storage_key, blob.size_bytes, blob.last_used_at.isoformat())
        report.blobs.append(item)
        if dry_run:
            item.assets_reset = db.scalar(
                func.count(AudioAsset.id).select().where(AudioAsset.blob_id == blob.id)
            ) or 0
            continue

        storage_key = blob.storage_key
        # 1) banco: quem usava o blob volta para a fila (gerar de novo recria o áudio) e o blob sai
        result = db.execute(
            update(AudioAsset)
            .where(AudioAsset.blob_id == blob.id)
            .values(
                status=STATUS_PENDING, storage_key=None, format=None, duration_ms=None, blob_id=None,
                error=None, updated_at=func.now(),
            ),
            execution_options={"synchronize_session": False},
        )
        item.assets_reset = result.rowcount
        repo.delete(blob)
        db.commit()

        # 2) armazenamento: só depois do commit. Uma falha aqui deixa só um arquivo órfão
        try:
            storage.delete(storage_key)
        except StorageError as exc:
            logger.warning("Não foi possível apagar o arquivo %s do cache: %s", storage_key, exc)
            report.file_errors.append(storage_key)

    return report


def format_report(report: PurgeReport) -> str:
    from app.modules.audio.cache.stats import format_size

    title = "Limpeza do cache de áudio (simulação: nada foi alterado)" if report.dry_run else "Limpeza do cache de áudio"
    verb = "seriam removidos" if report.dry_run else "removidos"
    lines = [title]
    for b in report.blobs:
        lines.append(
            f"  blob {b.blob_id}: {b.storage_key} ({format_size(b.size_bytes)}, último uso {b.last_used_at}, "
            f"{b.assets_reset} áudio(s) de volta para pending)"
        )
    lines.append(
        f"Total: {len(report.blobs)} arquivo(s) {verb}, {format_size(report.freed_bytes)}, "
        f"{report.assets_reset} áudio(s) de frase voltam para pending"
    )
    if report.file_errors:
        lines.append(f"Atenção: {len(report.file_errors)} arquivo(s) não saíram do armazenamento (ficaram órfãos)")
    return "\n".join(lines)
