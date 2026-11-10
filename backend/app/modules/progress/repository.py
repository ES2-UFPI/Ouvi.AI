"""Camada Repository: único ponto de acesso ao progresso de reprodução (PlaybackProgress)."""
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.progress.models import PlaybackProgress

DEFAULT_RECENT_LIMIT = 10


class PlaybackProgressRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: int, story_id: int) -> PlaybackProgress | None:
        stmt = select(PlaybackProgress).where(
            PlaybackProgress.user_id == user_id, PlaybackProgress.story_id == story_id
        )
        # populate_existing: se o objeto já estava na sessão, traz o estado atual do banco
        return self.db.scalars(stmt.execution_options(populate_existing=True)).one_or_none()

    def upsert(
        self,
        *,
        user_id: int,
        story_id: int,
        segment_position: int,
        offset_ms: int,
        client_time: datetime,
        filter_id: int | None = None,
        completed: bool = False,
    ) -> PlaybackProgress:
        """Cria o progresso, ou atualiza o que já existe, e devolve o que ficou valendo no banco.

        Tudo numa instrução só (`INSERT ... ON CONFLICT DO UPDATE`), então é seguro com chamadas
        simultâneas. O `WHERE` descarta uma gravação atrasada: se o `client_time` dela for mais antigo
        que o já salvo, nada muda, e o retorno é o progresso mais novo.
        """
        stmt = insert(PlaybackProgress).values(
            user_id=user_id,
            story_id=story_id,
            filter_id=filter_id,
            segment_position=segment_position,
            offset_ms=offset_ms,
            completed=completed,
            client_time=client_time,
        )
        new = stmt.excluded  # os valores que esta gravação tentou inserir
        stmt = stmt.on_conflict_do_update(
            constraint="uq_playback_progress_user_story",
            set_={
                "filter_id": new.filter_id,
                "segment_position": new.segment_position,
                "offset_ms": new.offset_ms,
                "completed": new.completed,
                "client_time": new.client_time,
                "updated_at": func.now(),
            },
            where=PlaybackProgress.__table__.c.client_time <= new.client_time,
        )
        self.db.execute(stmt)
        self.db.commit()
        progress = self.get(user_id, story_id)
        if progress is None:  # não acontece: acabou de ser gravado (ou já existia)
            raise RuntimeError("Progresso não encontrado logo depois do upsert")
        return progress

    def delete(self, user_id: int, story_id: int) -> bool:
        """Apaga o progresso ("Recomeçar"). Devolve False se não havia nada para apagar."""
        result = self.db.execute(
            delete(PlaybackProgress).where(
                PlaybackProgress.user_id == user_id, PlaybackProgress.story_id == story_id
            )
        )
        self.db.commit()
        return result.rowcount > 0

    def list_recent(
        self, user_id: int, *, limit: int = DEFAULT_RECENT_LIMIT, include_completed: bool = False
    ) -> list[PlaybackProgress]:
        """Progressos do usuário, do mais recente para o mais antigo (pelo `client_time`).

        Por padrão, só as histórias em andamento: as concluídas não aparecem em "Continuar ouvindo".
        """
        if limit < 1:
            raise ValueError(f"limit precisa ser pelo menos 1: {limit}")
        stmt = select(PlaybackProgress).where(PlaybackProgress.user_id == user_id)
        if not include_completed:
            stmt = stmt.where(PlaybackProgress.completed.is_(False))
        stmt = stmt.order_by(PlaybackProgress.client_time.desc(), PlaybackProgress.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))
