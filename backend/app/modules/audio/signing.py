"""URLs assinadas para o áudio.

A tag `<audio>` do navegador não consegue enviar o header `Authorization`, então o token JWT não
serve para o streaming. Em vez dele, a API (já autenticada) entrega ao front uma URL com a chave do
arquivo, a hora em que ela expira e uma assinatura HMAC-SHA256 dessas duas informações. Só quem tem
o segredo do servidor consegue gerar uma assinatura válida, e trocar a chave ou a expiração na URL
invalida a assinatura.
"""
import hashlib
import hmac
import time
from collections.abc import Callable
from urllib.parse import urlencode


class AudioSignatureError(Exception):
    """A URL assinada não vale. O router responde 403 para qualquer uma das subclasses."""


class InvalidSignature(AudioSignatureError):
    """A assinatura não confere: a chave, a expiração ou a própria assinatura foram alteradas."""


class ExpiredSignature(AudioSignatureError):
    """A assinatura confere, mas o prazo da URL já passou."""


class AudioUrlSigner:
    def __init__(
        self,
        secret: str,
        ttl_seconds: int = 3600,
        clock: Callable[[], float] = time.time,  # injetável, para os testes controlarem a hora
    ) -> None:
        if not secret:
            raise ValueError("O segredo de assinatura do áudio não pode ser vazio")
        self._secret = secret.encode()
        self.ttl_seconds = ttl_seconds
        self._clock = clock

    def sign(self, key: str) -> dict[str, str]:
        """Parâmetros da query string que dão acesso à `key` até `agora + ttl_seconds`."""
        expires = int(self._clock()) + self.ttl_seconds
        return {"key": key, "expires": str(expires), "signature": self._signature(key, expires)}

    def query_string(self, key: str) -> str:
        """Pronta para colar depois de `/audio/stream?`."""
        return urlencode(self.sign(key))

    def verify(self, key: str, expires: int, signature: str) -> None:
        """Não devolve nada se a URL vale; levanta `InvalidSignature` ou `ExpiredSignature` se não."""
        # A assinatura é conferida antes do prazo: uma expiração adulterada é InvalidSignature
        # compare_digest leva o mesmo tempo acerte ou erre, para não vazar a assinatura por tempo de resposta
        if not hmac.compare_digest(self._signature(key, expires), signature):
            raise InvalidSignature(key)
        if self._clock() > expires:
            raise ExpiredSignature(key)

    def _signature(self, key: str, expires: int) -> str:
        # A expiração vem por último e só tem dígitos, então a mensagem nunca é ambígua,
        # mesmo que a chave tenha uma quebra de linha
        message = f"{key}\n{expires}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()
