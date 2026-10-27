from datetime import datetime

from pydantic import BaseModel


class AudioUrlRead(BaseModel):
    """URL que o player coloca direto no `src` da tag `<audio>`, sem precisar de token."""

    url: str
    expires_at: datetime
