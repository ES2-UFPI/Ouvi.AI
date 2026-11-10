"""Camada Repository: único ponto de acesso aos registros de áudio (AudioAsset)."""
import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.audio.models import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
    STATUS_READY,
    AudioAsset,
)
from app.modules.stories.models import Segment

MAX_ERROR_LENGTH = 2000

# Para cada estado de destino, de quais estados dá para chegar nele
_ALLOWED_FROM: dict[str, set[str]] = {
    STATUS_GENERATING: {STATUS_PENDING, STATUS_FAILED},  # começar, ou tentar de novo depois de uma falha
    STATUS_READY: {STATUS_GENERATING},
    STATUS_FAILED: {STATUS_GENERATING},
    STATUS_PENDING: {STATUS_GENERATING, STATUS_FAILED},  # frase presa, ou falha que volta para a fila
}


class InvalidTransition(Exception):
    """A mudança de estado não é permitida, ou outro processo mudou o estado antes."""


def compute_rules_hash(rules: dict[str, Any]) -> str:
    """SHA-256 das regras do filtro. O JSON é canônico (chaves em ordem, sem espaços), então a mesma
    regra escrita em outra ordem dá o mesmo hash."""
    canonical = json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AudioAssetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, asset_id: int) -> AudioAsset | None:
        return self.db.get(AudioAsset, asset_id)

    def get_or_create(self, *, story_id: int, segment_id: int, rules_hash: str, voice_id: str) -> AudioAsset:
        """Devolve o áudio da frase para as regras e a voz, criando como `pending` se ainda não existir.

        Seguro com chamadas simultâneas: o `ON CONFLICT DO NOTHING` do Postgres faz a segunda inserção
        esperar a primeira e não inserir nada, sem erro de chave duplicada. Depois, as duas leem o mesmo
        registro. Nunca altera um registro que já existe.
        """
        self.db.execute(
            insert(AudioAsset)
            .values(story_id=story_id, segment_id=segment_id, rules_hash=rules_hash, voice_id=voice_id)
            .on_conflict_do_nothing(constraint="uq_audio_assets_segment_rules_voice")
        )
        self.db.commit()
        stmt = select(AudioAsset).where(
            AudioAsset.segment_id == segment_id,
            AudioAsset.rules_hash == rules_hash,
            AudioAsset.voice_id == voice_id,
        )
        # populate_existing: se o objeto já estava na sessão, traz o estado atual do banco
        return self.db.scalars(stmt.execution_options(populate_existing=True)).one()

    def list_by_story(self, story_id: int, *, rules_hash: str, voice_id: str) -> list[AudioAsset]:
        """Áudios da história para as regras e a voz, na ordem das frases."""
        stmt = (
            select(AudioAsset)
            .join(Segment, Segment.id == AudioAsset.segment_id)
            .where(
                AudioAsset.story_id == story_id,
                AudioAsset.rules_hash == rules_hash,
                AudioAsset.voice_id == voice_id,
            )
            .order_by(Segment.position)
        )
        return list(self.db.scalars(stmt))

    # ---------- transições de estado ----------

    def start_generation(self, asset: AudioAsset) -> None:
        """pending/failed -> generating, contando mais uma tentativa."""
        self._transition(asset, STATUS_GENERATING, attempts=AudioAsset.attempts + 1)

    def mark_ready(self, asset: AudioAsset, *, storage_key: str, audio_format: str, duration_ms: int) -> None:
        """generating -> ready, com o arquivo gravado no armazenamento."""
        if not storage_key or not audio_format:
            raise ValueError("storage_key e audio_format são obrigatórios")
        if duration_ms < 0:
            raise ValueError(f"duration_ms não pode ser negativo: {duration_ms}")
        self._transition(
            asset,
            STATUS_READY,
            storage_key=storage_key,
            format=audio_format,
            duration_ms=duration_ms,
            error=None,
        )

    def mark_failed(self, asset: AudioAsset, error: str) -> None:
        """generating -> failed, guardando o motivo."""
        self._transition(asset, STATUS_FAILED, error=error[:MAX_ERROR_LENGTH])

    def reset_to_pending(self, asset: AudioAsset) -> None:
        """generating/failed -> pending: volta para a fila."""
        self._transition(asset, STATUS_PENDING)

    def reset_stale(self, *, older_than: timedelta) -> int:
        """Volta para `pending` as frases em `generating` sem mudança há mais de `older_than` (o worker
        morreu no meio, por exemplo num reinício da API). Devolve quantas voltaram."""
        result = self.db.execute(
            update(AudioAsset)
            .where(
                AudioAsset.status == STATUS_GENERATING,
                AudioAsset.updated_at < func.now() - older_than,
            )
            .values(status=STATUS_PENDING, updated_at=func.now()),
            execution_options={"synchronize_session": False},
        )
        self.db.commit()
        return result.rowcount

    def _transition(self, asset: AudioAsset, target: str, **values: Any) -> None:
        """Muda o estado só se ele ainda for o que o objeto conhece (`WHERE status = <atual>`).

        Se outro processo mudou antes (dois workers pegando a mesma frase, por exemplo), nenhuma linha é
        alterada e a transição é recusada: só um deles segue.
        """
        current = asset.status
        if current not in _ALLOWED_FROM[target]:
            raise InvalidTransition(f"Áudio {asset.id}: transição {current} -> {target} não é permitida")

        result = self.db.execute(
            update(AudioAsset)
            .where(AudioAsset.id == asset.id, AudioAsset.status == current)
            .values(status=target, updated_at=func.now(), **values),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount == 0:
            self.db.rollback()
            raise InvalidTransition(
                f"Áudio {asset.id}: o estado mudou antes da transição {current} -> {target}"
            )
        self.db.commit()
        self.db.refresh(asset)
