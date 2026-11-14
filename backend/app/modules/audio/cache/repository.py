"""Camada Repository do cache de áudio: único ponto de acesso aos registros AudioBlob."""
import hashlib
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.audio.models import AudioBlob


def advisory_lock_id(cache_key: str) -> int:
    """Número do lock consultivo do Postgres para a chave: os 8 primeiros bytes do SHA-256, com sinal
    (o `pg_advisory_xact_lock` recebe um bigint)."""
    return int.from_bytes(hashlib.sha256(cache_key.encode("utf-8")).digest()[:8], "big", signed=True)


class AudioBlobRepository:
    """Nenhum método daqui faz `commit`: quem chama decide quando confirmar (o AudioCache segura um lock até
    o fim da transação, e um commit no meio o soltaria antes da hora)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, blob_id: int) -> AudioBlob | None:
        return self.db.get(AudioBlob, blob_id)

    def get_by_key(self, cache_key: str) -> AudioBlob | None:
        stmt = select(AudioBlob).where(AudioBlob.cache_key == cache_key)
        # populate_existing: se o objeto já estava na sessão, traz o estado atual do banco
        return self.db.scalars(stmt.execution_options(populate_existing=True)).one_or_none()

    def lock(self, cache_key: str) -> None:
        """Lock consultivo da chave até o fim da transação atual (commit ou rollback).

        Dois pedidos da mesma frase nova, mesmo em processos diferentes: o segundo espera aqui o primeiro
        sintetizar e registrar o blob, e depois o encontra pronto (uma única chamada ao TTS).
        """
        self.db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": advisory_lock_id(cache_key)})

    def create_if_absent(
        self,
        *,
        cache_key: str,
        storage_key: str,
        audio_format: str,
        duration_ms: int,
        size_bytes: int,
        char_count: int,
    ) -> AudioBlob:
        """Registra o blob da chave, ou devolve o que já existe (nunca altera um registro existente).

        Seguro com chamadas simultâneas: o `ON CONFLICT DO NOTHING` faz a segunda inserção esperar a primeira
        e não inserir nada, sem erro de chave duplicada. Depois, as duas leem o mesmo registro.
        """
        self.db.execute(
            insert(AudioBlob)
            .values(
                cache_key=cache_key,
                storage_key=storage_key,
                format=audio_format,
                duration_ms=duration_ms,
                size_bytes=size_bytes,
                char_count=char_count,
            )
            .on_conflict_do_nothing(constraint="uq_audio_blobs_cache_key")
        )
        blob = self.get_by_key(cache_key)
        assert blob is not None  # acabou de ser inserido (ou já existia)
        return blob

    def register_hit(self, blob: AudioBlob) -> None:
        """Mais um reaproveitamento: soma um acerto e atualiza o último uso (a limpeza olha para ele)."""
        self.db.execute(
            update(AudioBlob)
            .where(AudioBlob.id == blob.id)
            .values(hit_count=AudioBlob.hit_count + 1, last_used_at=func.now()),
            execution_options={"synchronize_session": False},
        )
        self.db.refresh(blob)

    def replace_file(
        self, blob: AudioBlob, *, storage_key: str, audio_format: str, duration_ms: int, size_bytes: int
    ) -> None:
        """O arquivo do blob sumiu e foi gerado de novo: corrige o registro e conta mais um erro de cache."""
        self.db.execute(
            update(AudioBlob)
            .where(AudioBlob.id == blob.id)
            .values(
                storage_key=storage_key,
                format=audio_format,
                duration_ms=duration_ms,
                size_bytes=size_bytes,
                miss_count=AudioBlob.miss_count + 1,
                last_used_at=func.now(),
            ),
            execution_options={"synchronize_session": False},
        )
        self.db.refresh(blob)

    def list_least_recently_used(self) -> list[AudioBlob]:
        """Todos os blobs, do uso mais antigo para o mais recente (a ordem da limpeza)."""
        return list(self.db.scalars(select(AudioBlob).order_by(AudioBlob.last_used_at, AudioBlob.id)))

    def list_unused_since(self, cutoff: datetime) -> list[AudioBlob]:
        """Blobs sem uso desde `cutoff`, do uso mais antigo para o mais recente."""
        stmt = (
            select(AudioBlob)
            .where(AudioBlob.last_used_at < cutoff)
            .order_by(AudioBlob.last_used_at, AudioBlob.id)
        )
        return list(self.db.scalars(stmt))

    def totals(self) -> dict[str, int]:
        """Somatórios do cache inteiro, para as estatísticas. Só lê."""
        row = self.db.execute(
            select(
                func.count(AudioBlob.id),
                func.coalesce(func.sum(AudioBlob.size_bytes), 0),
                func.coalesce(func.sum(AudioBlob.hit_count), 0),
                func.coalesce(func.sum(AudioBlob.miss_count), 0),
                func.coalesce(func.sum(AudioBlob.hit_count * AudioBlob.char_count), 0),
            )
        ).one()
        files, size, hits, misses, saved = (int(v) for v in row)
        return {"files": files, "size_bytes": size, "hits": hits, "misses": misses, "chars_saved": saved}

    def delete(self, blob: AudioBlob) -> None:
        self.db.delete(blob)
        self.db.flush()
