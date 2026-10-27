"""Adaptador S3 com boto3. Funciona com qualquer serviço compatível: MinIO (dev) e Cloudflare R2 (prod).

Este é o ÚNICO módulo que importa o boto3. Toda exceção dele é traduzida para as exceções de
`base.py` antes de sair daqui.
"""
from collections.abc import Iterator
from contextlib import contextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.integrations.storage.base import (
    InvalidByteRange,
    ObjectStorage,
    StorageError,
    StorageObjectNotFound,
    check_range,
)

# Códigos que o S3/MinIO/R2 devolvem para "não existe". O HEAD não tem corpo, então só traz o status.
_NOT_FOUND_CODES = {"NoSuchKey", "NotFound", "404", "NoSuchBucket"}


@contextmanager
def _translate_errors(key: str = "") -> Iterator[None]:
    """Converte as exceções do boto3 nas exceções do contrato."""
    try:
        yield
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in _NOT_FOUND_CODES:
            raise StorageObjectNotFound(key) from None
        if code == "InvalidRange":
            raise InvalidByteRange(f"Faixa inválida para {key!r}") from None
        raise StorageError(f"Erro do armazenamento ({code}): {exc}") from None
    except BotoCoreError as exc:  # ex.: MinIO fora do ar, endpoint errado
        raise StorageError(f"Armazenamento indisponível: {exc}") from None


class S3Storage(ObjectStorage):
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        public_endpoint: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.region = region
        self._client = self._make_client(endpoint, access_key, secret_key, region)
        # A assinatura da URL inclui o host. Dentro do Docker a API fala com `minio:9000`, mas o
        # navegador só enxerga `localhost:9000`, então a URL assinada usa um client próprio
        self._public_client = (
            self._make_client(public_endpoint, access_key, secret_key, region)
            if public_endpoint and public_endpoint != endpoint
            else self._client
        )

    @staticmethod
    def _make_client(endpoint: str, access_key: str, secret_key: str, region: str):
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            # path-style (host/bucket/chave): o MinIO local não tem DNS para bucket.host
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                # Os padrões do boto3 (60 s por tentativa, várias tentativas) travam a API por
                # minutos quando o MinIO está fora do ar; melhor falhar rápido
                connect_timeout=3,
                read_timeout=30,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        with _translate_errors(key):
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        with _translate_errors(key):
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def get_range(self, key: str, start: int, end: int) -> bytes:
        check_range(start, end)
        with _translate_errors(key):
            response = self._client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")
            return response["Body"].read()

    def size(self, key: str) -> int:
        with _translate_errors(key):
            return self._client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]

    def delete(self, key: str) -> None:
        with _translate_errors(key):
            self._client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        with _translate_errors(key):
            return self._public_client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
            )

    def ensure_bucket(self) -> None:
        try:
            with _translate_errors():
                self._client.head_bucket(Bucket=self.bucket)
            return
        except StorageObjectNotFound:
            pass
        with _translate_errors():
            # Fora da us-east-1 o S3 exige dizer a região na criação; o R2 usa a região "auto"
            if self.region in ("us-east-1", "auto"):
                self._client.create_bucket(Bucket=self.bucket)
            else:
                self._client.create_bucket(
                    Bucket=self.bucket,
                    CreateBucketConfiguration={"LocationConstraint": self.region},
                )
